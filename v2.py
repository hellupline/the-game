#!/usr/bin/env -S uv run python3

# lancer walk in turns

import sys
import time
from enum import StrEnum
from enum import auto
from operator import itemgetter
from pathlib import Path
from typing import Any
from typing import ClassVar
from typing import Literal
from typing import Self
from uuid import UUID
from uuid import uuid4

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

WALKING_SPEED = 2
RUNNING_SPEED = 6
ALERT_SPRITE_TIME = 6
ANIMATION_SPEED = 4


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
        self._running = True
        while self._running:
            self.run_once()
            pygame.display.flip()
            _ = self.clock.tick(FPS)

    def run_once(self: Self) -> None:
        self.handle_events(pygame.event.get())
        self.state_manager.dispatch()
        self.state_manager.update()
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
        width, height = self.state_manager.map_data.get_size()
        map_rect = pygame.rect.FRect((0, 0), (width * _TILE_SIZE, height * _TILE_SIZE))
        map_surface = pygame.surface.Surface(map_rect.size)
        _ = map_surface.fill(BLACK)
        self.draw_map(map_surface)
        self.draw_debug(map_surface)
        self.draw_characters(map_surface)
        viewport_rect = self.surface.get_rect()
        viewport_rect.center = self.state_manager.player.rect.topleft
        viewport_rect.clamp_ip(map_rect)
        _ = self.surface.blit(map_surface, area=viewport_rect)

    def draw_map(self: Self, surface: pygame.surface.Surface) -> None:
        for (x, y), tile in self.state_manager.map_data.data.items():
            if tile == TileType.WALL:
                rect = pygame.rect.Rect((x * _TILE_SIZE, y * _TILE_SIZE), TILE_SIZE)
                _ = pygame.draw.rect(surface, WALL_COLOR, rect)
            elif tile == TileType.WARP:
                rect = pygame.rect.Rect((x * _TILE_SIZE, y * _TILE_SIZE), TILE_SIZE)
                _ = pygame.draw.rect(surface, FLOOR_COLOR, rect)
                _ = pygame.draw.circle(surface, BLUE, rect.center, _TILE_SIZE // 4)

    def draw_characters(self: Self, surface: pygame.surface.Surface) -> None:
        characters = [*self.state_manager.map_lancers, self.state_manager.player]
        for character in sorted(characters, key=lambda c: c.rect.y):
            _ = surface.blit(character.surface, character.rect)

    def draw_debug(self: Self, surface: pygame.surface.Surface) -> None:
        self._draw_grid(surface)
        self._draw_lancer_path(surface)
        self._draw_lancer_line_of_sight(surface)

    def _draw_grid(self: Self, surface: pygame.surface.Surface) -> None:
        rect = surface.get_rect()
        for x in range(0, rect.width, _TILE_SIZE):
            _ = pygame.draw.line(surface, BLUE, (x, 0), (x, rect.height))
        for y in range(0, rect.height, _TILE_SIZE):
            _ = pygame.draw.line(surface, BLUE, (0, y), (rect.width, y))

    def _draw_lancer_path(self: Self, surface: pygame.surface.Surface) -> None:
        inflate = -_TILE_SIZE * 0.75
        for lancer in self.state_manager.map_lancers:
            for position in lancer.route.items:
                x, y = position
                pos = (x * _TILE_SIZE, y * _TILE_SIZE)
                rect = pygame.rect.Rect(pos, TILE_SIZE).inflate(inflate, inflate)
                if position == lancer.route.next():
                    _ = pygame.draw.rect(surface, LANCER_ROUTE_NEXT_COLOR, rect)
                else:
                    _ = pygame.draw.rect(surface, LANCER_ROUTE_COLOR, rect)

    def _draw_lancer_line_of_sight(self: Self, surface: pygame.surface.Surface) -> None:
        inflate = -_TILE_SIZE * 0.75
        for lancer in self.state_manager.map_lancers:
            for position in lancer.get_line_of_sight():
                x, y = position
                pos = (x * _TILE_SIZE, y * _TILE_SIZE)
                rect = pygame.rect.FRect(pos, TILE_SIZE).inflate(inflate, inflate)
                _ = pygame.draw.rect(surface, LANCER_RAYCAST_COLOR, rect, width=1)


class GameStateManager:
    window: GameWindow
    map_data: MapData
    map_lancers: list[Lancer]
    player: Player
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
        self.map_lancers = [
            Lancer(self, position, route)
            for position, route in zip(
                self.map_data.lancer_positions,
                self.map_data.lancer_routes,
                strict=True,
            )
        ]
        self.player = Player(self, self.map_data.player_position)

    def dispatch(self: Self) -> None:
        self.dispatch__lancers()
        self.handle_keys__player(pygame.key.get_pressed())

    def dispatch__lancers(self: Self) -> None:
        if triggered := self.get_triggered_lancers():
            for lancer in triggered:
                print(lancer.id, "triggered")  # noqa: T201
            return
        for lancer in self.map_lancers:
            if not lancer.is_moving and lancer.move(next(lancer.route)):
                lancer.route.advance()

    def get_triggered_lancers(self: Self) -> list[Lancer]:
        player_position = self.player.position
        if self.player.is_moving:
            player_position = self.player.next_position
        return [
            lancer
            for lancer in self.map_lancers
            if not lancer.is_moving and player_position in lancer.get_line_of_sight()
        ]

    def handle_keys__player(self: Self, keys: pygame.key.ScancodeWrapper) -> None:
        if self.player.is_moving:
            return
        x, y = self.player.position
        if keys[pygame.constants.K_DOWN]:
            _ = self.player.move((x, y + 1))
        elif keys[pygame.constants.K_UP]:
            _ = self.player.move((x, y - 1))
        elif keys[pygame.constants.K_RIGHT]:
            _ = self.player.move((x + 1, y))
        elif keys[pygame.constants.K_LEFT]:
            _ = self.player.move((x - 1, y))
        if keys[pygame.constants.K_LSHIFT]:
            self.player.movement_speed = MovementSpeed.RUNNING
        else:
            self.player.movement_speed = MovementSpeed.WALKING

    def update(self: Self) -> None:
        for lancer in self.map_lancers:
            _ = lancer.update()
        _ = self.player.update()

    def character__notify_new_position(self: Self, character: Character) -> None:
        print(character, f"{time.time():.1f}")  # noqa: T201

    def map__can_walk(
        self: Self,
        position: pygame.typing.Point,
        collision_key: Literal["player", "lancer"],
    ) -> bool:
        def get_position(character: Character) -> pygame.typing.Point:
            if character.next_position is not None:
                return character.next_position
            return character.position

        if collision_key == "player" and any(position == p for p in map(get_position, self.map_lancers)):
            return False
        if collision_key == "lancer" and position == get_position(self.player):
            return False
        return self.map_data.is_walkable(position)


class MapData:
    data: dict[pygame.typing.Point, TileType]
    lancer_positions: list[pygame.typing.Point]
    lancer_routes: list[list[pygame.typing.Point]]
    player_position: pygame.typing.Point

    def __init__(
        self: Self,
        map_filename: Path,
        lancer_routes_filenames: list[Path],
    ) -> None:
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


class Character:
    _character_type: ClassVar[Literal["player", "lancer"]]
    id: UUID
    state_manager: GameStateManager
    position: pygame.typing.Point
    surface: pygame.surface.Surface
    rect: pygame.rect.Rect
    hitbox: pygame.rect.Rect
    direction: Direction
    movement_speed: MovementSpeed
    next_position: pygame.typing.Point | None  # for grid & collision
    next_hitbox_position: pygame.typing.Point | None  # for drawing
    is_moving: bool
    _sprites: dict[Direction, pygame.surface.Surface]

    def __init__(
        self: Self,
        state_manager: GameStateManager,
        position: pygame.typing.Point,
        sprites: dict[Direction, pygame.surface.Surface],
    ) -> None:
        self._sprites = sprites
        self.id = uuid4()
        self.state_manager = state_manager
        self.surface = sprites[Direction.DOWN]
        self.rect = self.surface.get_rect()
        self.hitbox = pygame.rect.Rect((0, 0), TILE_SIZE)
        self.direction = Direction.DOWN
        self.movement_speed = MovementSpeed.WALKING
        self.set_position(position)
        self.unset_next_position()

    def __init_subclass__(cls: type[Self], charater_type: Literal["player", "lancer"], **kwargs: Any) -> None:  # pyright: ignore[reportAny, reportExplicitAny]  # noqa: ANN401
        super().__init_subclass__(**kwargs)
        cls._character_type = charater_type

    def set_position(self: Self, position: pygame.typing.Point) -> None:
        x, y = position
        self.position = position
        self.hitbox.topleft = (x * _TILE_SIZE, y * _TILE_SIZE)
        self.rect.midbottom = self.hitbox.midbottom

    def set_next_position(self: Self, position: pygame.typing.Point) -> None:
        x, y = position
        self.next_position = position
        self.next_hitbox_position = (x * _TILE_SIZE, y * _TILE_SIZE)
        self.is_moving = True

    def unset_next_position(self: Self) -> None:
        self.next_position = None
        self.next_hitbox_position = None
        self.is_moving = False

    def move(self: Self, position: pygame.typing.Point) -> bool:
        if (direction := self.get_direction(position)) != self.direction:
            self.direction = direction
            return False
        if not self.state_manager.map__can_walk(position, collision_key=self._character_type):
            return False
        self.set_next_position(position)
        return True

    def get_direction(self: Self, position: pygame.typing.Point) -> Direction:
        current_x, current_y = self.position
        x, y = position
        if y > current_y:
            return Direction.DOWN
        if y < current_y:
            return Direction.UP
        if x > current_x:
            return Direction.RIGHT
        if x < current_x:
            return Direction.LEFT
        return self.direction

    def update(self: Self) -> bool:
        self.surface = self._sprites[self.direction]
        if self.is_moving:
            return self.update__moving()
        return False

    def update__moving(self: Self) -> bool:
        if self.next_position is None or self.next_hitbox_position is None:
            return False
        if self.next_hitbox_position == self.hitbox.topleft:
            self.set_position(self.next_position)
            self.unset_next_position()
            self.state_manager.character__notify_new_position(self)
            return False
        max_distance = self.movement_speed.speed()
        current = pygame.math.Vector2(self.hitbox.topleft)
        current.move_towards_ip(self.next_hitbox_position, max_distance)
        self.hitbox.topleft = current
        self.rect.midbottom = self.hitbox.midbottom
        return True


class Player(Character, charater_type="player"):
    def __init__(
        self: Self,
        state_manager: GameStateManager,
        position: pygame.typing.Point,
    ) -> None:
        super().__init__(state_manager, position, get_character_sprite(GREEN))


class Lancer(Character, charater_type="lancer"):
    route: MovementGenerator[pygame.typing.Point]
    line_of_sight_distance: int

    def __init__(
        self: Self,
        state_manager: GameStateManager,
        position: pygame.typing.Point,
        route: list[pygame.typing.Point],
        line_of_sight_distance: int = 5,
    ) -> None:
        super().__init__(state_manager, position, get_character_sprite(YELLOW))
        self.route = MovementGenerator(route)
        self.line_of_sight_distance = line_of_sight_distance

    def get_line_of_sight(self: Self) -> list[pygame.typing.Point]:
        x, y = self.position
        dx, dy = {
            Direction.DOWN: (0, 1),
            Direction.UP: (0, -1),
            Direction.RIGHT: (1, 0),
            Direction.LEFT: (-1, 0),
        }[self.direction]
        line_of_sight: list[pygame.typing.Point] = []
        for i in range(1, self.line_of_sight_distance + 1):
            next_position = (x + dx * i, y + dy * i)
            # XXX: update to use the state manager collision detection
            # e.g., to avoid other characters
            if not self.state_manager.map_data.is_walkable(next_position):
                break
            line_of_sight.append(next_position)
        return line_of_sight


class MovementGenerator[T]:
    items: list[T]
    _counter: int = 0

    def __init__(self: Self, items: list[T]) -> None:
        self.items = items

    def __iter__(self: Self) -> Self:
        return self

    def __next__(self: Self) -> T:
        return self.next()

    def next(self: Self) -> T:
        try:
            return self.items[self._counter]
        except IndexError as exc:
            msg = "No items"
            raise StopIteration(msg) from exc

    def advance(self: Self) -> None:
        self._counter = (self._counter + 1) % len(self.items)


class Direction(StrEnum):
    DOWN = auto()
    UP = auto()
    RIGHT = auto()
    LEFT = auto()


class TileType(StrEnum):
    EMPTY = "."
    WALL = "H"
    WARP = "O"
    LANCER = "l"
    PLAYER = "p"


class MovementSpeed(StrEnum):
    WALKING = auto()
    RUNNING = auto()
    IDLE = auto()

    def speed(self: Self) -> int:
        if self == MovementSpeed.WALKING:
            return WALKING_SPEED
        if self == MovementSpeed.RUNNING:
            return RUNNING_SPEED
        return 0


def get_character_sprite(color: pygame.color.Color) -> dict[Direction, pygame.surface.Surface]:
    return {direction: _draw_character(direction, color) for direction in Direction}


def _draw_character(direction: Direction, color: pygame.color.Color) -> pygame.surface.Surface:
    head = pygame.rect.FRect((0, 0), TILE_SIZE).inflate(-_TILE_SIZE // 2, -_TILE_SIZE // 2)
    body = pygame.rect.FRect((0, _TILE_SIZE), TILE_SIZE)
    if direction == Direction.DOWN:
        head_polygon = [head.topleft, head.topright, head.midbottom, head.topleft]
    elif direction == Direction.UP:
        head_polygon = [head.bottomleft, head.bottomright, head.midtop, head.bottomleft]
    elif direction == Direction.RIGHT:
        head_polygon = [head.topleft, head.bottomleft, head.midright, head.topleft]
    elif direction == Direction.LEFT:
        head_polygon = [head.topright, head.bottomright, head.midleft, head.topright]
    body_polygon = [body.topleft, body.topright, body.midbottom, body.topleft]
    rect = pygame.rect.FRect((0, 0), (_TILE_SIZE, 2 * _TILE_SIZE))
    surface = pygame.surface.Surface(rect.size)
    surface.set_colorkey(COLORKEY)
    _ = surface.fill(COLORKEY)
    _ = pygame.draw.polygon(surface, color, head_polygon)
    _ = pygame.draw.polygon(surface, color, body_polygon)
    return surface


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
