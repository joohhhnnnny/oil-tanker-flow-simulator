"""
Strait and Tanker Renderer for the Oil Tanker Flow Simulation UI.

Handles all visual rendering of the strait, tankers, queue, and animations.
"""

from __future__ import annotations

import io
import math
import os
import urllib.error
import urllib.request
import pygame
from typing import List, Dict, Tuple
from dataclasses import dataclass

from ui_config import (
    Colors, TANKER_COLORS, TANKER_SIZES,
    STRAIT_X_START, STRAIT_X_END, STRAIT_Y_CENTER, MAP_HEIGHT, STRAIT_PANEL_WIDTH,
    QUEUE_Y_START, QUEUE_SPACING, FONT_SIZES,
    MAP_TILE_URL_TEMPLATE, MAP_TILE_CACHE_DIR, MAP_TILE_MIN_ZOOM, MAP_TILE_MAX_ZOOM,
    MAP_TILE_TIMEOUT_SECONDS, MAP_TILE_ATTRIBUTION,
)
from geo_layout import GeoViewport, build_projected_layout, interpolate_polyline, project_latlon
from ui_components import FontManager, draw_text


@dataclass
class VisualTanker:
    """Visual representation of a tanker for rendering."""

    tanker_id: int
    tanker_type: str
    status: str  # 'waiting', 'in_transit', 'completed', 'blocked'

    # Position (pixels)
    x: float = 0.0
    y: float = 0.0

    # Target position for smooth animation
    target_x: float = 0.0
    target_y: float = 0.0

    # Transit progress (0.0 to 1.0)
    progress: float = 0.0
    direction: str = "eastbound"  # eastbound (Persian Gulf -> Gulf of Oman) or westbound

    # Visual properties
    angle: float = 0.0  # Rotation angle
    wake_phase: float = 0.0  # For wake animation
    selected: bool = False

    # Queue position for waiting tankers
    queue_position: int = 0

    # Cargo info
    cargo_barrels: int = 0
    waiting_time: float = 0.0

    def update_position(self, speed: float = 0.15):
        """Smoothly move towards target position."""
        dx = self.target_x - self.x
        dy = self.target_y - self.y

        if abs(dx) > 0.5:
            self.x += dx * speed
        else:
            self.x = self.target_x

        if abs(dy) > 0.5:
            self.y += dy * speed
        else:
            self.y = self.target_y

        # Update wake animation
        if self.status == 'in_transit':
            self.wake_phase += 0.1


class StraitRenderer:
    """
    Renders the Strait of Hormuz visualization.

    Includes the waterway, land masses, channel markers, and geographical labels.
    """

    def __init__(self, surface_width: int, surface_height: int):
        self.width = surface_width
        self.height = surface_height
        self.viewport = GeoViewport()
        self.geo = build_projected_layout(self.width, self.height, self.viewport)
        self.tile_zoom = None
        self._has_tiles = False
        self._create_surfaces()

    def _create_surfaces(self):
        """Pre-render static elements."""
        # Create background surface for the strait
        self.background = pygame.Surface((self.width, self.height))
        self._draw_background()

    def _draw_background(self):
        """Draw the static background elements."""
        if self._draw_tile_basemap():
            self._draw_navigational_overlays()
            return

        self._draw_vector_basemap()
        self._draw_navigational_overlays()

    def _draw_vector_basemap(self):
        """Fallback background when online tiles are unavailable."""
        self.background.fill(Colors.WATER_DEEP)

        # Draw gradient water
        for y in range(self.height):
            # Create depth gradient
            depth_factor = 1.0 - abs(y - STRAIT_Y_CENTER) / (self.height / 2)
            r = int(Colors.WATER_DEEP[0] + (Colors.WATER_SHALLOW[0] - Colors.WATER_DEEP[0]) * depth_factor * 0.3)
            g = int(Colors.WATER_DEEP[1] + (Colors.WATER_SHALLOW[1] - Colors.WATER_DEEP[1]) * depth_factor * 0.3)
            b = int(Colors.WATER_DEEP[2] + (Colors.WATER_SHALLOW[2] - Colors.WATER_DEEP[2]) * depth_factor * 0.3)
            pygame.draw.line(self.background, (r, g, b), (0, y), (self.width, y))

        self._draw_graticule()

        # Fill land masses using projected coastlines.
        iran_polygon = [(0, 0), (self.width, 0), *self.geo.iran_coastline[::-1], (0, 0)]
        pygame.draw.polygon(self.background, Colors.LAND_IRAN, iran_polygon)

        arabia_polygon = [
            (0, self.height),
            (self.width, self.height),
            *self.geo.arabia_coastline[::-1],
            (0, self.height),
        ]
        pygame.draw.polygon(self.background, Colors.LAND_UAE, arabia_polygon)

        # Draw islands in a lighter sandy tone for map readability.
        island_color = tuple(min(255, c + 12) for c in Colors.LAND_UAE)
        for island in self.geo.islands:
            if len(island) >= 3:
                pygame.draw.polygon(self.background, island_color, island)
                pygame.draw.polygon(self.background, Colors.PANEL_BORDER, island, 1)

    def _draw_navigational_overlays(self):
        """Draw lane and separation overlays over either tile or vector basemap."""
        if len(self.geo.north_lane) > 1 and len(self.geo.south_lane) > 1:
            corridor = [*self.geo.north_lane, *reversed(self.geo.south_lane)]
            lane_fill = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            pygame.draw.polygon(lane_fill, (*Colors.WATER_CHANNEL, 70), corridor)
            self.background.blit(lane_fill, (0, 0))

        # Draw lane outlines first, then high-contrast dashes for visibility on map tiles.
        if len(self.geo.north_lane) > 1:
            pygame.draw.lines(self.background, (18, 92, 170), False, self.geo.north_lane, 3)
            self._draw_dashed_polyline(self.geo.north_lane, (125, 215, 255), dash_length=14)

        if len(self.geo.south_lane) > 1:
            pygame.draw.lines(self.background, (140, 70, 32), False, self.geo.south_lane, 3)
            self._draw_dashed_polyline(self.geo.south_lane, (255, 193, 128), dash_length=14)

        pygame.draw.lines(self.background, (96, 86, 40), False, self.geo.separation_line, 2)
        self._draw_dashed_polyline(self.geo.separation_line, Colors.TEXT_WARNING, dash_length=15)

    def _latlon_to_tile_pixel(self, lat: float, lon: float, zoom: int) -> Tuple[float, float]:
        """Convert lat/lon to global pixel coordinates at a Web Mercator zoom level."""
        lat = max(-85.0511, min(85.0511, lat))
        lat_rad = math.radians(lat)
        scale = 256 * (2 ** zoom)

        x = ((lon + 180.0) / 360.0) * scale
        y = (1.0 - (math.asinh(math.tan(lat_rad)) / math.pi)) * 0.5 * scale
        return x, y

    def _choose_tile_zoom(self) -> int:
        """Choose a zoom level that best matches viewport dimensions."""
        best_zoom = MAP_TILE_MIN_ZOOM
        best_score = float("inf")

        for zoom in range(MAP_TILE_MIN_ZOOM, MAP_TILE_MAX_ZOOM + 1):
            left, top = self._latlon_to_tile_pixel(self.viewport.max_lat, self.viewport.min_lon, zoom)
            right, bottom = self._latlon_to_tile_pixel(self.viewport.min_lat, self.viewport.max_lon, zoom)

            map_w = max(1.0, right - left)
            map_h = max(1.0, bottom - top)
            score = abs((map_w / self.width) - 1.0) + abs((map_h / self.height) - 1.0)
            if score < best_score:
                best_score = score
                best_zoom = zoom

        return best_zoom

    def _load_tile_image(self, zoom: int, x: int, y: int) -> pygame.Surface | None:
        """Load one tile from cache or remote provider."""
        max_idx = (2 ** zoom) - 1
        if y < 0 or y > max_idx:
            return None

        wrapped_x = x % (2 ** zoom)
        cache_path = os.path.join(MAP_TILE_CACHE_DIR, str(zoom), str(wrapped_x), f"{y}.png")

        if os.path.exists(cache_path):
            try:
                return pygame.image.load(cache_path).convert()
            except pygame.error:
                pass

        url = MAP_TILE_URL_TEMPLATE.format(z=zoom, x=wrapped_x, y=y)
        req = urllib.request.Request(url, headers={"User-Agent": "oil-tanker-flow-simulator/1.0"})

        try:
            with urllib.request.urlopen(req, timeout=MAP_TILE_TIMEOUT_SECONDS) as resp:
                data = resp.read()
            tile = pygame.image.load(io.BytesIO(data), "tile.png").convert()

            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            with open(cache_path, "wb") as f:
                f.write(data)
            return tile
        except (urllib.error.URLError, TimeoutError, OSError, pygame.error):
            return None

    def _draw_tile_basemap(self) -> bool:
        """Try to render realistic map tiles; returns True when successful."""
        self.tile_zoom = self._choose_tile_zoom()

        left, top = self._latlon_to_tile_pixel(self.viewport.max_lat, self.viewport.min_lon, self.tile_zoom)
        right, bottom = self._latlon_to_tile_pixel(self.viewport.min_lat, self.viewport.max_lon, self.tile_zoom)

        self._world_left = left
        self._world_top = top
        self._world_right = right
        self._world_bottom = bottom

        min_xtile = int(math.floor(left / 256))
        max_xtile = int(math.floor((right - 1) / 256))
        min_ytile = int(math.floor(top / 256))
        max_ytile = int(math.floor((bottom - 1) / 256))

        stitched_w = max(1, (max_xtile - min_xtile + 1) * 256)
        stitched_h = max(1, (max_ytile - min_ytile + 1) * 256)
        stitched = pygame.Surface((stitched_w, stitched_h))
        stitched.fill((90, 180, 215))

        loaded = 0
        for tile_x in range(min_xtile, max_xtile + 1):
            for tile_y in range(min_ytile, max_ytile + 1):
                tile = self._load_tile_image(self.tile_zoom, tile_x, tile_y)
                if tile is None:
                    continue
                loaded += 1
                stitched.blit(tile, ((tile_x - min_xtile) * 256, (tile_y - min_ytile) * 256))

        if loaded == 0:
            self._has_tiles = False
            return False

        crop_rect = pygame.Rect(
            int(left - min_xtile * 256),
            int(top - min_ytile * 256),
            max(1, int(right - left)),
            max(1, int(bottom - top)),
        )
        crop = stitched.subsurface(crop_rect).copy()
        self.background.blit(pygame.transform.smoothscale(crop, (self.width, self.height)), (0, 0))

        self._has_tiles = True
        return True

    def _draw_dashed_line(self, x1, y1, x2, y2, color, dash_length=5):
        """Draw a dashed line on the background."""
        dx = x2 - x1
        dy = y2 - y1
        distance = math.sqrt(dx * dx + dy * dy)
        dashes = int(distance / dash_length)

        for i in range(0, dashes, 2):
            start = i / dashes
            end = min((i + 1) / dashes, 1.0)
            pygame.draw.line(
                self.background,
                color,
                (x1 + dx * start, y1 + dy * start),
                (x1 + dx * end, y1 + dy * end),
                1
            )

    def _draw_dashed_polyline(self, points, color, dash_length=8):
        """Draw dashed segments over a multi-point polyline."""
        if len(points) < 2:
            return
        for i in range(len(points) - 1):
            x1, y1 = points[i]
            x2, y2 = points[i + 1]
            self._draw_dashed_line(x1, y1, x2, y2, color, dash_length=dash_length)

    def _draw_graticule(self):
        """Draw a subtle latitude/longitude grid to reinforce map orientation."""
        lon = self.viewport.min_lon
        while lon <= self.viewport.max_lon + 1e-6:
            x = int((lon - self.viewport.min_lon) / (self.viewport.max_lon - self.viewport.min_lon) * self.width)
            pygame.draw.line(self.background, Colors.GRID, (x, 0), (x, self.height), 1)
            lon += 0.5

        lat = self.viewport.min_lat
        while lat <= self.viewport.max_lat + 1e-6:
            y = int((self.viewport.max_lat - lat) / (self.viewport.max_lat - self.viewport.min_lat) * self.height)
            pygame.draw.line(self.background, Colors.GRID, (0, y), (self.width, y), 1)
            lat += 0.5

    def draw(self, surface: pygame.Surface, disruption_active: bool = False):
        """Draw the strait background."""
        surface.blit(self.background, (0, 0))

        if self._has_tiles:
            draw_text(surface, MAP_TILE_ATTRIBUTION, 8, self.height - 18,
                      Colors.TEXT_SECONDARY, FONT_SIZES["tiny"])

        # Draw disruption overlay if active
        if disruption_active:
            overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            overlay.fill((255, 50, 50, 25))
            surface.blit(overlay, (0, 0))

            # Draw warning stripes
            for i in range(0, self.width + self.height, 40):
                pygame.draw.line(
                    surface,
                    (255, 60, 60, 50),
                    (i, 0),
                    (i - self.height, self.height),
                    2
                )

    def draw_labels(self, surface: pygame.Surface):
        """Draw geographical labels."""
        def p(lat: float, lon: float) -> tuple[int, int]:
            return project_latlon(lat, lon, self.width, self.height, self.viewport)

        # Country labels
        iran_x, iran_y = p(28.2, 54.5)
        uae_x, uae_y = p(24.8, 54.1)
        oman_x, oman_y = p(23.7, 58.6)
        qatar_x, qatar_y = p(25.1, 52.5)
        bahrain_x, bahrain_y = p(26.2, 50.55)

        draw_text(surface, "IRAN", iran_x, iran_y, Colors.TEXT_SECONDARY, FONT_SIZES["header"], bold=True)
        draw_text(surface, "UNITED ARAB EMIRATES", uae_x, uae_y,
                  Colors.TEXT_SECONDARY, FONT_SIZES["small"])
        draw_text(surface, "OMAN", oman_x, oman_y,
                  Colors.TEXT_SECONDARY, FONT_SIZES["small"])
        draw_text(surface, "QATAR", qatar_x, qatar_y,
                  Colors.TEXT_SECONDARY, FONT_SIZES["small"])
        draw_text(surface, "BAHRAIN", bahrain_x, bahrain_y,
                  Colors.TEXT_SECONDARY, FONT_SIZES["tiny"])

        # Strait label
        strait_x, strait_y = p(26.15, 56.72)
        draw_text(surface, "STRAIT OF HORMUZ", strait_x - 55, strait_y - 12,
                  Colors.TEXT_PRIMARY, FONT_SIZES["small"], bold=True)

        # Direction arrows and labels
        pg_x, pg_y = p(26.7, 51.2)
        go_x, go_y = p(24.4, 58.4)
        draw_text(surface, "Persian Gulf", pg_x, pg_y,
                  Colors.TEXT_ACCENT, FONT_SIZES["small"])
        draw_text(surface, "Gulf of Oman", go_x, go_y,
                  Colors.TEXT_ACCENT, FONT_SIZES["small"])

        # Approximate coordinate references.
        draw_text(surface, "29N", 8, 6, Colors.TEXT_SECONDARY, FONT_SIZES["tiny"])
        draw_text(surface, "24N", 8, self.height - 80, Colors.TEXT_SECONDARY, FONT_SIZES["tiny"])
        draw_text(surface, "50E", 20, self.height - 20, Colors.TEXT_SECONDARY, FONT_SIZES["tiny"])
        draw_text(surface, "61E", self.width - 38, self.height - 20, Colors.TEXT_SECONDARY, FONT_SIZES["tiny"])

        # Draw lane direction arrows (eastbound top lane, westbound bottom lane).
        e_x, e_y = p(26.26, 56.45)
        w_x, w_y = p(26.00, 57.03)
        self._draw_arrow(surface, e_x - 20, e_y - 8, 40, Colors.TEXT_ACCENT)
        self._draw_arrow(surface, w_x + 20, w_y + 8, -40, Colors.TEXT_ACCENT)

        draw_text(surface, "NORTHBOUND LANE", e_x - 70, e_y - 30,
              (125, 215, 255), FONT_SIZES["tiny"], bold=True)
        draw_text(surface, "SOUTHBOUND LANE", w_x - 75, w_y + 18,
              (255, 193, 128), FONT_SIZES["tiny"], bold=True)

    def _draw_arrow(self, surface, x, y, length, color):
        """Draw a directional arrow, right for positive length, left for negative."""
        end_x = x + length
        direction = 1 if length >= 0 else -1
        pygame.draw.line(surface, color, (x, y), (x + length, y), 2)
        pygame.draw.polygon(surface, color, [
            (end_x, y),
            (end_x - (8 * direction), y - 5),
            (end_x - (8 * direction), y + 5)
        ])


class TankerRenderer:
    """
    Renders tanker vessels with different visual styles based on type and status.
    """

    def __init__(self):
        self._tanker_surfaces: Dict[str, pygame.Surface] = {}
        self._create_tanker_sprites()

    def _create_tanker_sprites(self):
        """Pre-render tanker sprites for each type."""
        for tanker_type, (width, height) in TANKER_SIZES.items():
            # Create surface with alpha
            surf = pygame.Surface((width + 10, height + 10), pygame.SRCALPHA)
            color = TANKER_COLORS.get(tanker_type, Colors.TANKER_WAITING)

            # Draw hull
            hull_rect = pygame.Rect(5, 5, width, height)
            pygame.draw.rect(surf, color, hull_rect, border_radius=3)

            # Draw deck details
            deck_color = tuple(max(0, c - 30) for c in color)
            pygame.draw.rect(surf, deck_color,
                             pygame.Rect(8, 7, width - 6, height - 4), border_radius=2)

            # Draw bridge (small rectangle at back)
            bridge_color = tuple(min(255, c + 40) for c in color)
            pygame.draw.rect(surf, bridge_color,
                             pygame.Rect(width - 5, (height - 4) // 2 + 3, 8, 6))

            self._tanker_surfaces[tanker_type] = surf

    def draw_tanker(
        self,
        surface: pygame.Surface,
        tanker: VisualTanker,
        show_label: bool = True
    ):
        """Draw a single tanker."""
        # Get base sprite
        sprite = self._tanker_surfaces.get(tanker.tanker_type)
        if not sprite:
            return

        # Create modified sprite based on status
        if tanker.status == 'blocked':
            # Red tint for blocked
            modified = sprite.copy()
            modified.fill((255, 0, 0, 100), special_flags=pygame.BLEND_RGBA_ADD)
            sprite = modified
        elif tanker.status == 'waiting':
            # Slight gray for waiting
            modified = sprite.copy()
            modified.fill((50, 50, 50, 0), special_flags=pygame.BLEND_RGBA_SUB)
            sprite = modified

        # Selection highlight
        if tanker.selected:
            # Draw selection ring
            size = TANKER_SIZES.get(tanker.tanker_type, (30, 12))
            pygame.draw.ellipse(
                surface,
                Colors.TEXT_ACCENT,
                (tanker.x - size[0] // 2 - 5, tanker.y - size[1] // 2 - 5,
                 size[0] + 10, size[1] + 10),
                2
            )

        # Rotate if needed (for transit direction)
        if tanker.angle != 0:
            sprite = pygame.transform.rotate(sprite, tanker.angle)

        # Draw sprite centered at position
        rect = sprite.get_rect(center=(tanker.x, tanker.y))
        surface.blit(sprite, rect)

        # Draw wake effect for moving tankers
        if tanker.status == 'in_transit':
            self._draw_wake(surface, tanker)

        # Draw label if enabled
        if show_label and tanker.selected:
            self._draw_tanker_info(surface, tanker)

    def _draw_wake(self, surface: pygame.Surface, tanker: VisualTanker):
        """Draw wake effect behind moving tanker."""
        size = TANKER_SIZES.get(tanker.tanker_type, (30, 12))

        # Wake lines
        for i in range(3):
            offset = i * 8 + int(tanker.wake_phase) % 8

            direction = 1 if tanker.direction == "eastbound" else -1
            start_x = tanker.x - direction * (size[0] // 2 + offset)
            pygame.draw.line(
                surface,
                Colors.WATER_SHALLOW,
                (start_x, tanker.y - 3 - i),
                (start_x - 10 * direction, tanker.y - 6 - i * 2),
                1
            )
            pygame.draw.line(
                surface,
                Colors.WATER_SHALLOW,
                (start_x, tanker.y + 3 + i),
                (start_x - 10 * direction, tanker.y + 6 + i * 2),
                1
            )

    def _draw_tanker_info(self, surface: pygame.Surface, tanker: VisualTanker):
        """Draw info popup for selected tanker."""
        # Info box position
        box_x = tanker.x + 30
        box_y = tanker.y - 40
        box_width = 140
        box_height = 70

        # Keep on screen
        if box_x + box_width > surface.get_width():
            box_x = tanker.x - box_width - 30

        # Draw box
        pygame.draw.rect(surface, Colors.PANEL_BG,
                         (box_x, box_y, box_width, box_height), border_radius=5)
        pygame.draw.rect(surface, Colors.TEXT_ACCENT,
                         (box_x, box_y, box_width, box_height), width=1, border_radius=5)

        # Draw info
        font = FontManager.get(FONT_SIZES["tiny"])
        y_offset = box_y + 8

        texts = [
            f"ID: {tanker.tanker_id}",
            f"Type: {tanker.tanker_type}",
            f"Status: {tanker.status}",
            f"Cargo: {tanker.cargo_barrels / 1e6:.1f}M bbl"
        ]

        for text in texts:
            text_surf = font.render(text, True, Colors.TEXT_PRIMARY)
            surface.blit(text_surf, (box_x + 8, y_offset))
            y_offset += 15


class QueueRenderer:
    """Renders the waiting queue visualization."""

    def __init__(self):
        self.max_visible = 15  # Maximum tankers to show in queue visualization
        self.left_queue_x = STRAIT_X_START + 12
        self.right_queue_x = STRAIT_X_END - 58

    def draw(
        self,
        surface: pygame.Surface,
        waiting_tankers: List[VisualTanker],
        tanker_renderer: TankerRenderer
    ):
        """Draw waiting queues for both traffic directions."""
        eastbound = [t for t in waiting_tankers if t.direction == "eastbound"]
        westbound = [t for t in waiting_tankers if t.direction == "westbound"]

        self._draw_direction_queue(
            surface,
            tankers=eastbound,
            tanker_renderer=tanker_renderer,
            queue_x=self.left_queue_x,
            label="EASTBOUND",
            align_left=True,
        )
        self._draw_direction_queue(
            surface,
            tankers=westbound,
            tanker_renderer=tanker_renderer,
            queue_x=self.right_queue_x,
            label="WESTBOUND",
            align_left=False,
        )

    def _draw_direction_queue(
        self,
        surface: pygame.Surface,
        tankers: List[VisualTanker],
        tanker_renderer: TankerRenderer,
        queue_x: int,
        label: str,
        align_left: bool,
    ):
        visible = min(len(tankers), self.max_visible)
        queue_height = visible * QUEUE_SPACING + 62
        panel_width = 100
        panel_x = queue_x - 54
        queue_rect = pygame.Rect(panel_x, QUEUE_Y_START - 40, panel_width, queue_height)
        pygame.draw.rect(surface, (*Colors.PANEL_BG, 180), queue_rect, border_radius=8)
        pygame.draw.rect(surface, Colors.PANEL_BORDER, queue_rect, width=1, border_radius=8)

        draw_text(surface, label, panel_x + 8, QUEUE_Y_START - 30,
                  Colors.TEXT_SECONDARY, FONT_SIZES["tiny"], bold=True)

        for i, tanker in enumerate(tankers[:self.max_visible]):
            tanker.queue_position = i
            tanker.target_x = queue_x
            tanker.target_y = QUEUE_Y_START + i * QUEUE_SPACING
            tanker.angle = 0 if tanker.direction == "eastbound" else 180
            tanker.update_position(speed=0.2)
            tanker_renderer.draw_tanker(surface, tanker, show_label=False)

            offset_x = -36 if align_left else 30
            draw_text(surface, str(i + 1), int(tanker.x + offset_x), int(tanker.y - 6),
                      Colors.TEXT_SECONDARY, FONT_SIZES["tiny"])

        if len(tankers) > self.max_visible:
            overflow = len(tankers) - self.max_visible
            draw_text(surface, f"+{overflow} more", panel_x + 8,
                      QUEUE_Y_START + self.max_visible * QUEUE_SPACING,
                      Colors.TEXT_WARNING, FONT_SIZES["tiny"])


class TransitRenderer:
    """Renders tankers in transit through the strait."""

    def __init__(self):
        self.geo = build_projected_layout(STRAIT_PANEL_WIDTH, MAP_HEIGHT)
        self.eastbound_lane = self.geo.north_lane
        self.westbound_lane = list(reversed(self.geo.south_lane))

    def update_transit_position(self, tanker: VisualTanker):
        """Update tanker position based on transit progress."""
        lane = self.eastbound_lane if tanker.direction == "eastbound" else self.westbound_lane
        x, y = interpolate_polyline(lane, tanker.progress)
        tanker.target_x = x
        tanker.target_y = y
        tanker.angle = 0 if tanker.direction == "eastbound" else 180

        tanker.update_position(speed=0.1)

    def draw(
        self,
        surface: pygame.Surface,
        transit_tankers: List[VisualTanker],
        tanker_renderer: TankerRenderer
    ):
        """Draw tankers in transit."""
        for tanker in transit_tankers:
            self.update_transit_position(tanker)
            tanker_renderer.draw_tanker(surface, tanker)
