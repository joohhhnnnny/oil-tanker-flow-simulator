"""
UI Components for the Oil Tanker Flow Simulation.

Reusable UI widgets: buttons, panels, labels, progress bars, etc.
"""

from __future__ import annotations

import pygame
from typing import Callable, Optional, Tuple, List
from dataclasses import dataclass, field

from ui_config import Colors, FONT_SIZES


class FontManager:
    """Manages fonts for the UI."""

    _fonts: dict = {}
    _initialized: bool = False

    @classmethod
    def initialize(cls):
        """Initialize pygame fonts."""
        if not cls._initialized:
            pygame.font.init()
            cls._initialized = True

    @classmethod
    def get(cls, size: int, bold: bool = False) -> pygame.font.Font:
        """Get a font of the specified size."""
        cls.initialize()
        key = (size, bold)
        if key not in cls._fonts:
            try:
                font_name = "DejaVu Sans" if not bold else "DejaVu Sans Bold"
                cls._fonts[key] = pygame.font.SysFont(font_name, size)
            except Exception:
                cls._fonts[key] = pygame.font.Font(None, size)
        return cls._fonts[key]


@dataclass
class Button:
    """Interactive button widget."""

    x: int
    y: int
    width: int
    height: int
    text: str
    callback: Optional[Callable] = None
    enabled: bool = True
    toggle: bool = False
    toggled: bool = False

    # Visual state
    _hovered: bool = field(default=False, repr=False)
    _pressed: bool = field(default=False, repr=False)

    def contains(self, pos: Tuple[int, int]) -> bool:
        """Check if position is within button bounds."""
        return (self.x <= pos[0] <= self.x + self.width and
                self.y <= pos[1] <= self.y + self.height)

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle mouse events. Returns True if button was clicked."""
        if not self.enabled:
            return False

        if event.type == pygame.MOUSEMOTION:
            self._hovered = self.contains(event.pos)

        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.contains(event.pos):
                self._pressed = True

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self._pressed and self.contains(event.pos):
                self._pressed = False
                if self.toggle:
                    self.toggled = not self.toggled
                if self.callback:
                    self.callback()
                return True
            self._pressed = False

        return False

    def draw(self, surface: pygame.Surface):
        """Render the button."""
        # Determine color based on state
        if not self.enabled:
            color = Colors.BUTTON_DISABLED
            text_color = Colors.TEXT_SECONDARY
        elif self._pressed or (self.toggle and self.toggled):
            color = Colors.BUTTON_ACTIVE
            text_color = Colors.TEXT_PRIMARY
        elif self._hovered:
            color = Colors.BUTTON_HOVER
            text_color = Colors.TEXT_PRIMARY
        else:
            color = Colors.BUTTON_NORMAL
            text_color = Colors.TEXT_SECONDARY

        # Draw button background
        rect = pygame.Rect(self.x, self.y, self.width, self.height)
        pygame.draw.rect(surface, color, rect, border_radius=6)
        pygame.draw.rect(surface, Colors.PANEL_BORDER, rect, width=1, border_radius=6)

        # Draw text
        font = FontManager.get(FONT_SIZES["normal"])
        text_surface = font.render(self.text, True, text_color)
        text_rect = text_surface.get_rect(center=rect.center)
        surface.blit(text_surface, text_rect)


@dataclass
class Panel:
    """Container panel with optional title."""

    x: int
    y: int
    width: int
    height: int
    title: Optional[str] = None
    bg_color: Tuple[int, int, int] = Colors.PANEL_BG

    def draw(self, surface: pygame.Surface):
        """Render the panel."""
        # Background
        rect = pygame.Rect(self.x, self.y, self.width, self.height)
        pygame.draw.rect(surface, self.bg_color, rect)
        pygame.draw.rect(surface, Colors.PANEL_BORDER, rect, width=1)

        # Title
        if self.title:
            font = FontManager.get(FONT_SIZES["header"], bold=True)
            title_surface = font.render(self.title, True, Colors.TEXT_PRIMARY)
            surface.blit(title_surface, (self.x + 15, self.y + 10))

            # Title underline
            line_y = self.y + 38
            pygame.draw.line(
                surface,
                Colors.PANEL_BORDER,
                (self.x + 10, line_y),
                (self.x + self.width - 10, line_y),
                1
            )


class Label:
    """Text label widget."""

    def __init__(
        self,
        x: int,
        y: int,
        text: str,
        color: Tuple[int, int, int] = Colors.TEXT_PRIMARY,
        size: int = FONT_SIZES["normal"],
        bold: bool = False
    ):
        self.x = x
        self.y = y
        self.text = text
        self.color = color
        self.size = size
        self.bold = bold

    def draw(self, surface: pygame.Surface):
        """Render the label."""
        font = FontManager.get(self.size, self.bold)
        text_surface = font.render(self.text, True, self.color)
        surface.blit(text_surface, (self.x, self.y))

    def set_text(self, text: str):
        """Update label text."""
        self.text = text


class ProgressBar:
    """Horizontal progress bar widget."""

    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        value: float = 0.0,
        max_value: float = 100.0,
        color: Tuple[int, int, int] = Colors.TEXT_ACCENT,
        bg_color: Tuple[int, int, int] = Colors.PANEL_BG,
        show_text: bool = True
    ):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.value = value
        self.max_value = max_value
        self.color = color
        self.bg_color = bg_color
        self.show_text = show_text

    def set_value(self, value: float):
        """Update progress value."""
        self.value = max(0, min(value, self.max_value))

    def draw(self, surface: pygame.Surface):
        """Render the progress bar."""
        # Background
        bg_rect = pygame.Rect(self.x, self.y, self.width, self.height)
        pygame.draw.rect(surface, self.bg_color, bg_rect, border_radius=4)
        pygame.draw.rect(surface, Colors.PANEL_BORDER, bg_rect, width=1, border_radius=4)

        # Progress fill
        if self.max_value > 0:
            fill_width = int((self.value / self.max_value) * (self.width - 4))
            if fill_width > 0:
                fill_rect = pygame.Rect(self.x + 2, self.y + 2, fill_width, self.height - 4)
                pygame.draw.rect(surface, self.color, fill_rect, border_radius=3)

        # Text
        if self.show_text:
            percentage = (self.value / self.max_value * 100) if self.max_value > 0 else 0
            font = FontManager.get(FONT_SIZES["small"])
            text = f"{percentage:.0f}%"
            text_surface = font.render(text, True, Colors.TEXT_PRIMARY)
            text_rect = text_surface.get_rect(center=bg_rect.center)
            surface.blit(text_surface, text_rect)


class StatRow:
    """A row displaying a statistic with label and value."""

    def __init__(
        self,
        x: int,
        y: int,
        label: str,
        value: str = "0",
        label_width: int = 150,
        value_color: Tuple[int, int, int] = Colors.TEXT_ACCENT
    ):
        self.x = x
        self.y = y
        self.label = label
        self.value = value
        self.label_width = label_width
        self.value_color = value_color

    def set_value(self, value: str, color: Optional[Tuple[int, int, int]] = None):
        """Update the displayed value."""
        self.value = value
        if color:
            self.value_color = color

    def draw(self, surface: pygame.Surface):
        """Render the stat row."""
        # Label
        font = FontManager.get(FONT_SIZES["small"])
        label_surface = font.render(self.label, True, Colors.TEXT_SECONDARY)
        surface.blit(label_surface, (self.x, self.y))

        # Value
        value_font = FontManager.get(FONT_SIZES["small"], bold=True)
        value_surface = value_font.render(str(self.value), True, self.value_color)
        surface.blit(value_surface, (self.x + self.label_width, self.y))


class StatusIndicator:
    """Circular status indicator with optional label."""

    def __init__(
        self,
        x: int,
        y: int,
        radius: int = 8,
        label: str = "",
        status: str = "normal"
    ):
        self.x = x
        self.y = y
        self.radius = radius
        self.label = label
        self.status = status

    def set_status(self, status: str):
        """Update status: 'normal', 'warning', 'critical', 'blocked'."""
        self.status = status

    def draw(self, surface: pygame.Surface):
        """Render the status indicator."""
        # Determine color
        colors = {
            "normal": Colors.STATUS_NORMAL,
            "warning": Colors.STATUS_WARNING,
            "critical": Colors.STATUS_CRITICAL,
            "blocked": Colors.STATUS_BLOCKED,
        }
        color = colors.get(self.status, Colors.STATUS_NORMAL)

        # Draw circle
        pygame.draw.circle(surface, color, (self.x, self.y), self.radius)
        pygame.draw.circle(surface, Colors.TEXT_PRIMARY, (self.x, self.y), self.radius, 1)

        # Draw label
        if self.label:
            font = FontManager.get(FONT_SIZES["small"])
            label_surface = font.render(self.label, True, Colors.TEXT_SECONDARY)
            surface.blit(label_surface, (self.x + self.radius + 8, self.y - 7))


class Dropdown:
    """Dropdown selection widget."""

    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        options: List[str],
        selected_index: int = 0,
        on_change: Optional[Callable[[int, str], None]] = None
    ):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.options = options
        self.selected_index = selected_index
        self.on_change = on_change
        self.enabled = True
        self._expanded = False
        self._hovered_index = -1

    @property
    def selected(self) -> str:
        """Get currently selected option."""
        return self.options[self.selected_index] if self.options else ""

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Handle mouse events."""
        if not self.enabled:
            self._expanded = False
            return False

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            # Check main button click
            main_rect = pygame.Rect(self.x, self.y, self.width, self.height)
            if main_rect.collidepoint(event.pos):
                self._expanded = not self._expanded
                return True

            # Check option clicks when expanded
            if self._expanded:
                for i, option in enumerate(self.options):
                    opt_rect = pygame.Rect(
                        self.x,
                        self.y + self.height + i * self.height,
                        self.width,
                        self.height
                    )
                    if opt_rect.collidepoint(event.pos):
                        self.selected_index = i
                        self._expanded = False
                        if self.on_change:
                            self.on_change(i, option)
                        return True

                # Click outside closes dropdown
                self._expanded = False

        elif event.type == pygame.MOUSEMOTION and self._expanded:
            self._hovered_index = -1
            for i in range(len(self.options)):
                opt_rect = pygame.Rect(
                    self.x,
                    self.y + self.height + i * self.height,
                    self.width,
                    self.height
                )
                if opt_rect.collidepoint(event.pos):
                    self._hovered_index = i
                    break

        return False

    def draw(self, surface: pygame.Surface):
        """Render the dropdown."""
        # Main button
        main_rect = pygame.Rect(self.x, self.y, self.width, self.height)
        bg_color = Colors.BUTTON_NORMAL if self.enabled else Colors.BUTTON_DISABLED
        text_color = Colors.TEXT_PRIMARY if self.enabled else Colors.TEXT_SECONDARY
        pygame.draw.rect(surface, bg_color, main_rect, border_radius=4)
        pygame.draw.rect(surface, Colors.PANEL_BORDER, main_rect, width=1, border_radius=4)

        # Selected text
        font = FontManager.get(FONT_SIZES["small"])
        text_surface = font.render(self.selected, True, text_color)
        surface.blit(text_surface, (self.x + 10, self.y + (self.height - text_surface.get_height()) // 2))

        # Arrow
        arrow_x = self.x + self.width - 20
        arrow_y = self.y + self.height // 2
        if self._expanded:
            points = [(arrow_x, arrow_y + 3), (arrow_x + 8, arrow_y + 3), (arrow_x + 4, arrow_y - 3)]
        else:
            points = [(arrow_x, arrow_y - 3), (arrow_x + 8, arrow_y - 3), (arrow_x + 4, arrow_y + 3)]
        pygame.draw.polygon(surface, Colors.TEXT_SECONDARY if self.enabled else Colors.PANEL_BORDER, points)

        # Expanded options
        if self._expanded and self.enabled:
            for i, option in enumerate(self.options):
                opt_rect = pygame.Rect(
                    self.x,
                    self.y + self.height + i * self.height,
                    self.width,
                    self.height
                )
                bg_color = Colors.BUTTON_HOVER if i == self._hovered_index else Colors.BUTTON_NORMAL
                pygame.draw.rect(surface, bg_color, opt_rect)
                pygame.draw.rect(surface, Colors.PANEL_BORDER, opt_rect, width=1)

                text_surface = font.render(option, True, Colors.TEXT_PRIMARY)
                surface.blit(text_surface, (opt_rect.x + 10, opt_rect.y + (self.height - text_surface.get_height()) // 2))


def draw_text(
    surface: pygame.Surface,
    text: str,
    x: int,
    y: int,
    color: Tuple[int, int, int] = Colors.TEXT_PRIMARY,
    size: int = FONT_SIZES["normal"],
    bold: bool = False,
    center: bool = False
):
    """Utility function to draw text."""
    font = FontManager.get(size, bold)
    text_surface = font.render(text, True, color)
    if center:
        text_rect = text_surface.get_rect(center=(x, y))
        surface.blit(text_surface, text_rect)
    else:
        surface.blit(text_surface, (x, y))
