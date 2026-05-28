"""Minimal Pygame 2D arm twin for validating gesture commands.

Install the extra dependency with:
    uv pip install pygame
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame


Color = tuple[int, int, int]
Point = tuple[int, int]


@dataclass
class JointLimits:
    low: float
    high: float


class Arm2D:
    """Simple 3-DoF planar arm rendered in an X/Z side view."""

    def __init__(self, width: int = 520, height: int = 420, fps: int = 30) -> None:
        pygame.init()
        self.width = width
        self.height = height
        self.fps = fps
        self.screen = pygame.display.set_mode((width, height))
        pygame.display.set_caption("2D Arm Twin")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("arial", 18)
        self.running = True

        self.origin = (width // 2, height - 70)
        self.link_lengths = (92.0, 82.0, 56.0)
        self.home_angles = (90.0, -35.0, 25.0)
        self.angles = list(self.home_angles)
        self.limits = (
            JointLimits(10.0, 170.0),
            JointLimits(-115.0, 35.0),
            JointLimits(-105.0, 125.0),
        )
        self._toggle_latched = False
        self.last_command: str | None = None

    def update(self, command: str | None) -> None:
        """Apply one bounded command step to the arm state."""
        self._handle_events()
        if not self.running:
            return

        if command is None or command == "STOP":
            self._toggle_latched = False
            self.last_command = command
            return

        step = 4.0
        if command == "HOME":
            self.angles = list(self.home_angles)
            self._toggle_latched = False
        elif command in {"STEP_X", "STEP_X_POS"}:
            self.angles[0] -= step
            self._toggle_latched = False
        elif command in {"STEP_X_NEG"}:
            self.angles[0] += step
            self._toggle_latched = False
        elif command in {"STEP_Z_PLUS", "STEP_Z_POS"}:
            self.angles[1] += step
            self.angles[2] += step * 0.5
            self._toggle_latched = False
        elif command in {"STEP_Z_MINUS", "STEP_Z_NEG"}:
            self.angles[1] -= step
            self.angles[2] -= step * 0.5
            self._toggle_latched = False
        elif command in {"TOGGLE", "TOGGLE_MODE"} and not self._toggle_latched:
            self.angles[2] *= -1.0
            self._toggle_latched = True

        self.angles = [
            max(limit.low, min(limit.high, angle))
            for angle, limit in zip(self.angles, self.limits)
        ]
        self.last_command = command

    def draw(self) -> None:
        """Render the current arm pose."""
        if not self.running:
            return

        bg: Color = (245, 247, 250)
        link_color: Color = (43, 79, 116)
        joint_color: Color = (229, 122, 68)
        ee_color: Color = (35, 145, 100)
        axis_color: Color = (185, 193, 203)

        self.screen.fill(bg)
        pygame.draw.line(
            self.screen,
            axis_color,
            (40, self.origin[1]),
            (self.width - 40, self.origin[1]),
            1,
        )
        pygame.draw.line(
            self.screen,
            axis_color,
            (self.origin[0], 35),
            (self.origin[0], self.height - 35),
            1,
        )

        points = self.forward_kinematics()
        for start, end in zip(points, points[1:]):
            pygame.draw.line(self.screen, link_color, start, end, 9)

        for point in points[:-1]:
            pygame.draw.circle(self.screen, joint_color, point, 13)
            pygame.draw.circle(self.screen, (255, 255, 255), point, 5)
        pygame.draw.circle(self.screen, ee_color, points[-1], 10)

        self._draw_text(f"command: {self.last_command or 'None'}", (16, 16))
        angle_text = "angles: " + ", ".join(f"{a:.0f}" for a in self.angles)
        self._draw_text(angle_text, (16, 40))
        pygame.display.flip()
        self.clock.tick(self.fps)

    def forward_kinematics(self) -> list[Point]:
        """Return base, intermediate joints, and end-effector screen points."""
        x, z = 0.0, 0.0
        total_angle = 0.0
        points = [self._world_to_screen(x, z)]

        for length, angle in zip(self.link_lengths, self.angles):
            total_angle += math.radians(angle)
            x += length * math.cos(total_angle)
            z += length * math.sin(total_angle)
            points.append(self._world_to_screen(x, z))

        return points

    def close(self) -> None:
        pygame.quit()

    def _handle_events(self) -> None:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False

    def _world_to_screen(self, x: float, z: float) -> Point:
        return int(self.origin[0] + x), int(self.origin[1] - z)

    def _draw_text(self, text: str, pos: Point) -> None:
        surface = self.font.render(text, True, (32, 38, 45))
        self.screen.blit(surface, pos)


if __name__ == "__main__":
    arm = Arm2D()
    demo_commands = ["HOME", "STEP_Z_POS", "STEP_X_POS", "STEP_Z_NEG", "STOP"]
    index = 0
    try:
        while arm.running:
            arm.update(demo_commands[index // 35 % len(demo_commands)])
            arm.draw()
            index += 1
    finally:
        arm.close()
