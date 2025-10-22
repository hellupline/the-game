#!/usr/bin/env -S uv run python3

# create lancer
# lancer walk in turns

import sys
from enum import StrEnum
from operator import itemgetter
from pathlib import Path
from typing import Self

import pygame
import pygame.base
import pygame.color
import pygame.constants
import pygame.display
import pygame.event
import pygame.key
import pygame.math
import pygame.surface
import pygame.time
import pygame.typing

BLACK = pygame.color.Color(64, 64, 64)
GREY = pygame.color.Color(128, 128, 128)
WHITE = pygame.color.Color(240, 240, 240)
RED = pygame.color.Color(240, 64, 64)
GREEN = pygame.color.Color(64, 240, 64)
BLUE = pygame.color.Color(64, 64, 240)
CYAN = pygame.color.Color(64, 240, 240)
MAGENTA = pygame.color.Color(240, 64, 240)
YELLOW = pygame.color.Color(240, 240, 64)

_TILE_SIZE = 32
TILE_SIZE = (_TILE_SIZE, _TILE_SIZE)
WINDOW_SIZE = (30 * _TILE_SIZE, 20 * _TILE_SIZE)
FPS = 60

WALL_COLOR = WHITE
FLOOR_COLOR = BLACK
WARP_COLOR = BLUE
PLAYER_COLOR = GREEN
LANCER_COLOR = YELLOW
LANCER_CHASING_COLOR = RED
LANCER_DONE_COLOR = GREY
LANCER_ROUTE_COLOR = CYAN
LANCER_ROUTE_NEXT_COLOR = YELLOW
LANCER_RAYCAST_COLOR = MAGENTA
COLORKEY = pygame.color.Color(255, 0, 255)

WALKING_SPEED = 200
RUNNING_SPEED = 500
ALERT_SPRITE_TIME = 0.6
ANIMATION_SPEED = 4.0


class GameWindow:
    surface: pygame.surface.Surface
    font: pygame.font.Font
    clock: pygame.time.Clock
    state_manager: GameStateManager
    _running: bool

    def __init__(self: Self) -> None:
        self.surface = pygame.display.set_mode(WINDOW_SIZE)
        self.font = pygame.font.Font(pygame.font.get_default_font())
        self.clock = pygame.time.Clock()
        self.state_manager = GameStateManager(window=self)
        self._running = True

    def quit(self: Self) -> None:
        self._running = False

    def run(self: Self) -> None:
        dt = 0
        self._running = True
        while self._running:
            self.run_once(0.001)
            pygame.display.flip()
            dt = self.clock.tick(FPS) / 1000

    def run_once(self: Self, dt: float) -> None:
        self.handle_events(pygame.event.get())
        self.draw()

    def handle_events(self: Self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if event.type == pygame.constants.QUIT:
                self.quit()
                return
            quit_keys = (pygame.constants.K_ESCAPE, pygame.constants.K_q)
            if event.type == pygame.constants.KEYDOWN and event.key in quit_keys:  # pyright: ignore[reportAny]
                self.quit()
                return

    def draw(self: Self) -> None:
        self.draw_map(self.surface)
        self.draw_debug(self.surface)

    def draw_map(self: Self, surface: pygame.surface.Surface) -> None:
        for (x, y), tile in self.state_manager.map_data.data.items():
            if tile == TileType.WALL:
                rect = pygame.rect.FRect((x * _TILE_SIZE, y * _TILE_SIZE), TILE_SIZE)
                _ = pygame.draw.rect(surface, WALL_COLOR, rect)
            elif tile == TileType.WARP:
                rect = pygame.rect.FRect((x * _TILE_SIZE, y * _TILE_SIZE), TILE_SIZE)
                _ = pygame.draw.rect(surface, FLOOR_COLOR, rect)
                _ = pygame.draw.circle(surface, BLUE, rect.center, _TILE_SIZE // 4)

    def draw_debug(self: Self, surface: pygame.surface.Surface) -> None:
        self._draw_grid(surface)

    def _draw_grid(self: Self, surface: pygame.surface.Surface) -> None:  # pyright: ignore[reportUnusedParameter]
        rect = surface.get_rect()
        for x in range(0, rect.width, _TILE_SIZE):
            _ = pygame.draw.line(surface, BLUE, (x, 0), (x, rect.height))
        for y in range(0, rect.height, _TILE_SIZE):
            _ = pygame.draw.line(surface, BLUE, (0, y), (rect.width, y))


class GameStateManager:
    window: GameWindow
    map_data: MapData
    _map_cache: dict[str, MapData]

    def __init__(self: Self, window: GameWindow) -> None:
        self.window = window
        self.load_maps()
        self.set_map("map1")

    def load_maps(self: Self) -> None:
        self._map_cache = {
            "map1": MapData(
                map_filename=Path("./map1.txt"),
                lancer_routes_filenames=[Path("./map1_lancer1.txt"), Path("./map1_lancer2.txt")],
            ),
            "map2": MapData(
                map_filename=Path("./map2.txt"),
                lancer_routes_filenames=[Path("./map2_lancer1.txt")],
            ),
        }

    def set_map(self: Self, map_name: str) -> None:
        self.map_data = self._map_cache[map_name]


class MapData:
    data: dict[pygame.typing.Point, TileType]
    lancer_positions: list[pygame.typing.Point]
    lancer_routes: list[list[pygame.typing.Point]]
    player_position: pygame.typing.Point

    def __init__(self: Self, map_filename: Path, lancer_routes_filenames: list[Path]) -> None:
        self.data = {}
        self.lancer_positions = []
        self.lancer_routes = []
        self.load_map(map_filename)
        self.load_lancer_routes(lancer_routes_filenames)

    def load_map(self: Self, map_filename: Path) -> None:
        map_data = map_filename.read_text().strip()
        for y, row in enumerate(map_data.splitlines()):
            for x, tile in enumerate(map(TileType, row)):
                if tile in (TileType.EMPTY, TileType.WALL, TileType.WARP):
                    self.data[(x, y)] = TileType(tile)
                elif tile == TileType.LANCER:
                    self.lancer_positions.append((x, y))
                elif tile == TileType.PLAYER:
                    self.player_position = (x, y)

    def load_lancer_routes(self: Self, lancer_routes_filenames: list[Path]) -> None:
        for filaneme in lancer_routes_filenames:
            path = filaneme.read_text().strip()
            items = [
                ((x, y), sequence)
                for y, row in enumerate(path.splitlines())
                for x, sequence in enumerate(row)
                if sequence not in (".",)
            ]
            items = sorted(items, key=itemgetter(1))
            self.lancer_routes.append([*map(itemgetter(0), items)])

    def get_size(self: Self) -> pygame.typing.Point:
        return (self.get_width(), self.get_height())

    def get_width(self: Self) -> float:
        return max(x for x, _ in self.data) + 1

    def get_height(self: Self) -> float:
        return max(y for _, y in self.data) + 1

    def is_walkable(self: Self, position: pygame.typing.Point) -> bool:
        return self.data.get(position) != TileType.WALL

    def is_warp(self: Self, position: pygame.typing.Point) -> bool:
        return self.data.get(position) == TileType.WARP


class TileType(StrEnum):
    EMPTY = "."
    WALL = "H"
    WARP = "O"
    LANCER = "l"
    PLAYER = "p"


def main() -> None:
    pygame.display.set_caption("The Game")
    _ = pygame.base.init()
    GameWindow().run()
    pygame.quit()
    sys.exit()


MAP1_NAME: str = "map1"

MAP2_NAME: str = "map2"
MAP2_DATA: str = Path("./map2.txt").read_text().strip()
MAP2_LANCER_ROUTES: list[str] = [
    # Path("./map2_lancer1.txt").read_text().strip(),  # noqa: ERA001
]

if __name__ == "__main__":
    main()
