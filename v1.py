#!/usr/bin/env -S uv run python3

from abc import ABC
from abc import ABCMeta
from abc import abstractmethod
from enum import StrEnum
from enum import auto
from operator import itemgetter
from typing import Any
from typing import ClassVar
from typing import Literal
from typing import Self
from typing import final
from typing import override
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

WALKING_SPEED = 200
RUNNING_SPEED = 500
ALERT_SPRITE_TIME = 0.6
ANIMATION_SPEED = 4.0


class Window:
    surface: pygame.surface.Surface
    font: pygame.font.Font | None
    clock: pygame.time.Clock
    _running: bool

    def __init__(
        self: Self,
        surface: pygame.surface.Surface,
        font: pygame.font.Font | None = None,
    ) -> None:
        self.surface = surface
        self.font = font
        self.clock = pygame.time.Clock()
        self._running = False

    def run(self: Self) -> None:
        dt = 0
        self._running = True
        while self._running:
            events = pygame.event.get()
            keys = pygame.key.get_pressed()
            self.handle_events(events)
            self.handle_keys(keys)
            _ = self.update(dt)
            self.draw(dt)
            pygame.display.flip()
            dt = self.clock.tick(FPS) / 1000

    def handle_events(self: Self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if event.type == pygame.constants.QUIT:
                self.quit()

    def handle_keys(self: Self, keys: pygame.key.ScancodeWrapper) -> None:  # pyright: ignore[reportUnusedParameter]
        pass

    def update(self: Self, dt: float) -> bool:  # pyright: ignore[reportUnusedParameter]  # noqa: ARG002
        """Return true if event should continue processing"""
        return True

    def draw(self: Self, dt: float) -> None:  # pyright: ignore[reportUnusedParameter]
        pass

    def quit(self: Self) -> None:
        self._running = False


class GameWindow(Window):
    state_manager: GameStateManager

    def __init__(self: Self) -> None:
        pygame.display.set_caption("The Game")
        surface = pygame.display.set_mode(WINDOW_SIZE)
        font = pygame.font.Font(pygame.font.get_default_font())
        super().__init__(surface, font)
        self.state_manager = GameStateManager(main_window=self)

    @override
    def handle_keys(self: Self, keys: pygame.key.ScancodeWrapper) -> None:
        if keys[pygame.constants.K_ESCAPE] or keys[pygame.constants.K_q]:
            self.quit()
            return
        self.state_manager.handle_keys(keys)

    @override
    def update(self: Self, dt: float) -> bool:
        return self.state_manager.update(dt)

    @override
    def draw(self: Self, dt: float) -> None:
        width, height = self.state_manager.map_data.get_size()
        map_rect = pygame.rect.FRect((0, 0), (width * _TILE_SIZE, height * _TILE_SIZE))
        surface = pygame.surface.Surface(map_rect.size)
        _ = surface.fill(BLACK)
        self.draw_map(surface, dt)
        self.draw_grid(surface, dt)
        self.draw_lancer_path(surface, dt)
        self.draw_lancer_line_of_sight(surface, dt)
        self.draw_characters(surface, dt)
        self.state_manager.draw(surface, dt)
        viewport_rect = self.surface.get_rect()
        viewport_rect.center = self.state_manager.player.rect.topleft
        viewport_rect.clamp_ip(map_rect)
        _ = self.surface.blit(surface, area=viewport_rect)

    def draw_map(self: Self, surface: pygame.surface.Surface, dt: float) -> None:  # pyright: ignore[reportUnusedParameter]  # noqa: ARG002
        for (x, y), tile in self.state_manager.map_data.data.items():
            if tile == TileType.WALL:
                rect = pygame.rect.FRect((x * _TILE_SIZE, y * _TILE_SIZE), TILE_SIZE)
                _ = pygame.draw.rect(surface, WALL_COLOR, rect)
            elif tile == TileType.WARP:
                rect = pygame.rect.FRect((x * _TILE_SIZE, y * _TILE_SIZE), TILE_SIZE)
                _ = pygame.draw.rect(surface, FLOOR_COLOR, rect)
                _ = pygame.draw.circle(surface, BLUE, rect.center, _TILE_SIZE // 4)

    def draw_characters(self: Self, surface: pygame.surface.Surface, dt: float) -> None:  # pyright: ignore[reportUnusedParameter]  # noqa: ARG002
        for lancer in self.state_manager.lancers:
            _ = surface.blit(lancer.surface, lancer.rect)
        _ = surface.blit(self.state_manager.player.surface, self.state_manager.player.rect)

    def draw_grid(self: Self, surface: pygame.surface.Surface, dt: float) -> None:  # pyright: ignore[reportUnusedParameter]  # noqa: ARG002
        rect = surface.get_rect()
        for x in range(0, rect.width, _TILE_SIZE):
            _ = pygame.draw.line(surface, BLUE, (x, 0), (x, rect.height))
        for y in range(0, rect.height, _TILE_SIZE):
            _ = pygame.draw.line(surface, BLUE, (0, y), (rect.width, y))

    def draw_lancer_path(self: Self, surface: pygame.surface.Surface, dt: float) -> None:  # pyright: ignore[reportUnusedParameter]  # noqa: ARG002
        inflate = -_TILE_SIZE * 0.75
        for lancer in self.state_manager.lancers:
            for position in lancer.patrol_route.items:
                x, y = position
                pos = (x * _TILE_SIZE, y * _TILE_SIZE)
                rect = pygame.rect.FRect(pos, TILE_SIZE).inflate(inflate, inflate)
                if position == lancer.patrol_route.next():
                    _ = pygame.draw.rect(surface, LANCER_ROUTE_NEXT_COLOR, rect)
                else:
                    _ = pygame.draw.rect(surface, LANCER_ROUTE_COLOR, rect)

    def draw_lancer_line_of_sight(self: Self, surface: pygame.surface.Surface, dt: float) -> None:  # pyright: ignore[reportUnusedParameter]  # noqa: ARG002
        inflate = -_TILE_SIZE * 0.75
        for lancer in self.state_manager.lancers:
            for position in lancer.get_line_of_sight():
                x, y = position
                pos = (x * _TILE_SIZE, y * _TILE_SIZE)
                rect = pygame.rect.FRect(pos, TILE_SIZE).inflate(inflate, inflate)
                _ = pygame.draw.rect(surface, LANCER_RAYCAST_COLOR, rect, width=1)


class GameStateManager:
    main_window: Window
    state: GameState
    game_events: list[GameEvent]
    map_data: MapData
    lancers: list[Lancer]
    player: Player
    _map_name: str
    _map_data_cache: dict[str, MapData]

    def __init__(self: Self, main_window: Window) -> None:
        self.main_window = main_window
        self.state = GameState.overworld
        self.game_events = []
        self._map_data_cache = {
            MAP1_NAME: MapData(map_data=MAP1_DATA, lancer_routes=MAP1_LANCER_ROUTES),
            MAP2_NAME: MapData(map_data=MAP2_DATA, lancer_routes=[]),
        }
        self.load_map(MAP1_NAME)

    def load_map(self: Self, map_name: str) -> None:
        self._map_name = map_name
        self.map_data = self._map_data_cache[map_name]
        self.lancers = [
            Lancer(game_state_manager=self, position=position, route=route)
            for position, route in zip(
                self.map_data.lancer_positions,
                self.map_data.lancer_routes,
                strict=True,
            )
        ]
        self.player = Player(game_state_manager=self, position=self.map_data.player_position)

    def handle_keys(self: Self, keys: pygame.key.ScancodeWrapper) -> None:
        self.handle_keys__player(keys)

    def handle_keys__player(self: Self, keys: pygame.key.ScancodeWrapper) -> None:
        if not self.player.is_moving:
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
            self.player.movement_type = MovementType.RUNNING
        else:
            self.player.movement_type = MovementType.WALKING

    def update(self: Self, dt: float) -> bool:
        if not self.update__game_events(dt):
            return False
        if not self.update__lancers(dt):
            return False
        if not self.update__player(dt):
            return False
        return self.dispatch()

    def update__game_events(self: Self, dt: float) -> bool:  # pyright: ignore[reportUnusedParameter]
        if not self.game_events:
            self.state = GameState.overworld
            return True
        for item in self.game_events:
            if not item.update(dt):
                self.game_events.remove(item)
            break
        return True

    def update__lancers(self: Self, dt: float) -> bool:
        for lancer in self.lancers:
            _ = lancer.update(dt)
        return True

    def update__player(self: Self, dt: float) -> bool:
        _ = self.player.update(dt)
        return True

    def dispatch(self: Self) -> bool:
        if self.state == GameState.overworld:
            return self.dispatch__update_lancers_patrol()
        if self.state == GameState.game_event:
            return True
        return True

    def dispatch__update_lancers_patrol(self: Self) -> bool:
        if triggered := [
            lancer
            for lancer in self.lancers
            if not lancer.is_moving
            and lancer.state == LancerState.patrolling
            and self.player.position in lancer.get_line_of_sight()
        ]:
            self.state = GameState.game_event
            for lancer in triggered:
                lancer.state = LancerState.triggered
            self.game_events.extend(AlertSprite(lancer) for lancer in triggered)
            return False
        if chasing := [
            lancer
            for lancer in self.lancers
            if not lancer.is_moving
            and lancer.state == LancerState.triggered
            and self.player.position in lancer.get_line_of_sight()
        ]:
            self.state = GameState.game_event
            for lancer in chasing:
                lancer.state = LancerState.chasing
            player = self.player
            main_surface = self.main_window.surface  # XXX: using incorrect surface ?
            self.game_events.extend(AlertDialog(lancer, player, main_surface) for lancer in chasing)
            return False
        for lancer in self.lancers:
            if lancer.is_moving:
                continue
            if lancer.state == LancerState.patrolling:
                next_position = next(lancer.patrol_route)
                if lancer.move(next_position):
                    lancer.patrol_route.advance()
        return True

    def draw(self: Self, surface: pygame.surface.Surface, dt: float) -> None:
        if self.game_events:
            _ = self.game_events[0].draw(surface, dt)

    def is_walkable(
        self: Self,
        position: pygame.typing.Point,
        collision_type: Literal["player", "lancer"],
    ) -> bool:
        if collision_type == "player" and any(
            position == p
            for lancer in self.lancers
            for p in (
                lancer.position,
                lancer.next_position,
            )
        ):
            return False
        if collision_type == "lancer" and position in (self.player.position, self.player.next_position):
            return False
        return self.map_data.is_walkable(position)


class GameEvent(ABC):
    @abstractmethod
    def update(self: Self, dt: float) -> bool:
        """Return false if event processing should stop"""
        raise NotImplementedError

    @abstractmethod
    def dispatch(self: Self, dt: float) -> bool:
        """Return false if event processing should stop"""
        raise NotImplementedError

    @abstractmethod
    def draw(self: Self, surface: pygame.surface.Surface, dt: float) -> bool:
        """Return false if event processing should stop"""
        raise NotImplementedError


class TimedGameEvent(GameEvent, metaclass=ABCMeta):
    _max_time: ClassVar[float]
    dt: float = 0.0

    def __init_subclass__(cls: type[Self], max_time: float, **kwargs: Any) -> None:  # pyright: ignore[reportAny, reportExplicitAny]  # noqa: ANN401
        super().__init_subclass__(**kwargs)
        cls._max_time = max_time

    @override
    def update(self: Self, dt: float) -> bool:
        self.dt += dt
        return not self.dt > ALERT_SPRITE_TIME


@final
class AlertSprite(TimedGameEvent, max_time=ALERT_SPRITE_TIME):
    surface: pygame.surface.Surface
    rect: pygame.rect.FRect
    lancer: Lancer
    _sprites: list[pygame.surface.Surface]
    _sprite_index: float = 0

    def __init__(self: Self, lancer: Lancer) -> None:
        sprites = _draw_alert_mark(RED)
        self.surface = sprites[0]
        self.rect = self.surface.get_frect()
        self._sprites = sprites
        self.lancer = lancer
        self.rect.midbottom = lancer.rect.midtop

    @override
    def update(self: Self, dt: float) -> bool:
        self._sprite_index = (self._sprite_index + ANIMATION_SPEED * dt) % len(self._sprites)
        self.surface = self._sprites[int(self._sprite_index)]
        return super().update(dt)

    @override
    def dispatch(self: Self, dt: float) -> bool:
        return True

    @override
    def draw(self: Self, surface: pygame.surface.Surface, dt: float) -> bool:
        _ = surface.blit(self.surface, self.rect)
        return True


@final
class AlertDialog(GameEvent):
    surface: pygame.surface.Surface
    rect: pygame.rect.FRect
    lancer: Lancer
    player: Player

    def __init__(self: Self, lancer: Lancer, player: Player, main_surface: pygame.surface.Surface) -> None:
        main_window_rect = main_surface.get_rect()
        self.rect = pygame.rect.FRect((0, 0), (main_window_rect.width, main_window_rect.height * 0.2))
        self.surface = pygame.surface.Surface(self.rect.size)
        self.lancer = lancer
        self.player = player
        self.rect.midbottom = main_window_rect.midbottom

    @override
    def update(self: Self, dt: float) -> bool:
        return True

    @override
    def dispatch(self: Self, dt: float) -> bool:
        return True

    @override
    def draw(self: Self, surface: pygame.surface.Surface, dt: float) -> bool:
        _ = surface.blit(self.surface, self.rect)
        return True


@final
class AlertSprite3(TimedGameEvent, max_time=ALERT_SPRITE_TIME):
    surface: pygame.surface.Surface
    rect: pygame.rect.FRect
    lancer: Lancer
    _sprites: list[pygame.surface.Surface]
    _sprite_index: float = 0

    def __init__(self: Self, lancer: Lancer) -> None:
        sprites = _draw_alert_mark(BLUE)
        self.surface = sprites[0]
        self.rect = self.surface.get_frect()
        self._sprites = sprites
        self.lancer = lancer
        self.rect.midbottom = lancer.rect.midtop

    @override
    def update(self: Self, dt: float) -> bool:
        self._sprite_index = (self._sprite_index + ANIMATION_SPEED * dt) % len(self._sprites)
        self.surface = self._sprites[int(self._sprite_index)]
        return super().update(dt)

    @override
    def dispatch(self: Self, dt: float) -> bool:
        return True

    @override
    def draw(self: Self, surface: pygame.surface.Surface, dt: float) -> bool:
        _ = surface.blit(self.surface, self.rect)
        return True


class MapData:
    data: dict[pygame.typing.Point, TileType]
    lancer_positions: list[pygame.typing.Point]
    lancer_routes: list[list[pygame.typing.Point]]
    player_position: pygame.typing.Point

    def __init__(self: Self, map_data: str, lancer_routes: list[str]) -> None:
        self.data = {}
        self.lancer_positions = []
        self.lancer_routes = []
        self.load_map(map_data)
        self.load_lancer_routes(lancer_routes)

    def load_map(self: Self, map_data: str) -> None:
        for y, row in enumerate(map_data.strip().splitlines()):
            for x, tile in enumerate(map(TileType, row)):
                if tile in (TileType.EMPTY, TileType.WALL, TileType.WARP):
                    self.data[(x, y)] = TileType(tile)
                elif tile in (TileType.LANCER1, TileType.LANCER2):
                    self.lancer_positions.append((x, y))
                elif tile == TileType.PLAYER:
                    self.player_position = (x, y)

    def load_lancer_routes(self: Self, lancer_routes: list[str]) -> None:
        for path in lancer_routes:
            items = [
                ((x, y), sequence)
                for y, row in enumerate(path.strip().splitlines())
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
    game_state_manager: GameStateManager
    position: pygame.typing.Point
    surface: pygame.surface.Surface
    rect: pygame.rect.FRect
    hitbox: pygame.rect.FRect
    direction: Direction
    movement_type: MovementType
    next_position: pygame.typing.Point | None = None  # for grid & collision
    next_hitbox_position: pygame.typing.Point | None = None  # for drawing
    is_moving: bool = False
    _sprites: dict[Direction, dict[MovementType, pygame.surface.Surface]]

    def __init__(
        self: Self,
        game_state_manager: GameStateManager,
        position: pygame.typing.Point,
        sprites: dict[Direction, dict[MovementType, pygame.surface.Surface]],
    ) -> None:
        self.id = uuid4()
        self.game_state_manager = game_state_manager
        self.position = position
        self.direction = Direction.DOWN
        self.movement_type = MovementType.WALKING
        self._sprites = sprites
        self.surface = self._sprites[self.direction][MovementType.IDLE]
        self.rect = self.surface.get_frect()
        self.hitbox = pygame.rect.FRect((0, 0), TILE_SIZE)
        self.set_position(position)

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
        if not self.game_state_manager.is_walkable(position, collision_type=self._character_type):
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

    def update(self: Self, dt: float) -> bool:
        self.surface = self._sprites[self.direction][MovementType.IDLE]
        if self.is_moving:
            return self.handle_moving(dt)
        return False

    def handle_moving(self: Self, dt: float) -> bool:
        if self.next_position is None or self.next_hitbox_position is None:
            return False
        if self.next_hitbox_position == self.hitbox.topleft:
            self.position = self.next_position
            self.unset_next_position()
            return False
        max_distance = self.movement_type.speed() * dt
        current = pygame.math.Vector2(self.hitbox.topleft)
        current.move_towards_ip(self.next_hitbox_position, max_distance)
        self.hitbox.topleft = current
        self.rect.midbottom = self.hitbox.midbottom
        return True


class Lancer(Character, charater_type="lancer"):
    state: LancerState
    patrol_route: MovementGenerator[pygame.typing.Point]
    line_of_sight_distance: int

    def __init__(
        self: Self,
        game_state_manager: GameStateManager,
        position: pygame.typing.Point,
        route: list[pygame.typing.Point],
        line_of_sight_distance: int = 5,
    ) -> None:
        super().__init__(game_state_manager, position, get_character_surface(LANCER_COLOR))
        self.state = LancerState.patrolling
        self.patrol_route = MovementGenerator(route)
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
            if not self.game_state_manager.map_data.is_walkable(next_position):
                break
            line_of_sight.append(next_position)
        return line_of_sight


class Player(Character, charater_type="player"):
    def __init__(self: Self, game_state_manager: GameStateManager, position: pygame.typing.Point) -> None:
        super().__init__(game_state_manager, position, get_character_surface(PLAYER_COLOR))


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


class MovementType(StrEnum):
    IDLE = auto()
    WALKING = auto()
    RUNNING = auto()

    def speed(self: Self) -> float:
        if self == MovementType.WALKING:
            return WALKING_SPEED
        if self == MovementType.RUNNING:
            return RUNNING_SPEED
        return 0.0


class TileType(StrEnum):
    EMPTY = "."
    WALL = "H"
    WARP = "O"
    LANCER1 = "1"
    LANCER2 = "2"
    PLAYER = "p"


class GameState(StrEnum):
    overworld = auto()
    game_event = auto()
    menu = auto()
    dialog = auto()
    player_found = auto()
    battle = auto()


class LancerState(StrEnum):
    patrolling = auto()
    triggered = auto()
    chasing = auto()
    done = auto()


def get_character_surface(
    color: pygame.color.Color,
) -> dict[Direction, dict[MovementType, pygame.surface.Surface]]:
    return {d: {m: _draw_direction_arrow(d, color) for m in MovementType} for d in Direction}


def _draw_direction_arrow(direction: Direction, color: pygame.color.Color) -> pygame.surface.Surface:
    head = pygame.rect.FRect((0, 0), TILE_SIZE)
    body = pygame.rect.FRect((0, _TILE_SIZE), TILE_SIZE)
    if direction == Direction.DOWN:
        pody_points = [body.topleft, body.topright, body.midbottom, body.topleft]
    elif direction == Direction.UP:
        pody_points = [body.bottomleft, body.bottomright, body.midtop, body.bottomleft]
    elif direction == Direction.RIGHT:
        pody_points = [body.topleft, body.bottomleft, body.midright, body.topleft]
    elif direction == Direction.LEFT:
        pody_points = [body.topright, body.bottomright, body.midleft, body.topright]
    rect = pygame.rect.FRect((0, 0), (_TILE_SIZE, 2 * _TILE_SIZE))
    surface = pygame.surface.Surface(rect.size)
    surface.set_colorkey(COLORKEY)
    _ = surface.fill(COLORKEY)
    _ = pygame.draw.circle(surface, color, head.center, _TILE_SIZE // 4)
    _ = pygame.draw.polygon(surface, color, pody_points)
    return surface


def _draw_alert_mark(color: pygame.color.Color) -> list[pygame.surface.Surface]:
    polygon_rect = pygame.rect.FRect((0, 0), TILE_SIZE)
    points_1 = [polygon_rect.midtop, polygon_rect.midright, polygon_rect.midbottom, polygon_rect.midleft]
    polygon_rect.inflate_ip(-_TILE_SIZE * 0.5, 0)
    points_2 = [polygon_rect.midtop, polygon_rect.midright, polygon_rect.midbottom, polygon_rect.midleft]
    polygon_rect.inflate_ip(-_TILE_SIZE * 0.5, 0)
    points_3 = [polygon_rect.midtop, polygon_rect.midright, polygon_rect.midbottom, polygon_rect.midleft]
    surface_rect = pygame.rect.FRect((0, 0), TILE_SIZE)
    surface_1 = pygame.surface.Surface(surface_rect.size)
    surface_2 = pygame.surface.Surface(surface_rect.size)
    surface_3 = pygame.surface.Surface(surface_rect.size)
    for surface, points in zip(
        [surface_1, surface_2, surface_3],
        [points_1, points_2, points_3],
        strict=False,
    ):
        surface.set_colorkey(COLORKEY)
        _ = surface.fill(COLORKEY)
        _ = pygame.draw.polygon(surface, color, points)
    return [surface_1, surface_2, surface_3]


def main() -> None:
    _ = pygame.base.init()
    GameWindow().run()


MAP1_NAME = "map1"
MAP1_DATA = """
HHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHH
H.....................................................................................H
H.HHHHH.....HHHHH......1........................................H.....H...............H
H.H.............H...............................................H.....H...............H
H.H.............H...............................................H.....H...............H
H.H.............H...............................................H.....H...............H
H.H...HHHHHHH...H...........................................HHHHH.....HHHHH...........H
H.....HHHHHHH.........................................................................H
H.....HHHHHHH.........................................................................H
H.....HHHHHHH.............p...........................................................H
H.....HHHHHHH.........................................................................H
H.....HHHHHHH.........................................................................H
H.H...HHHHHHH...H...........................................HHHHH.....HHHHH...........H
H.H.............H...............................................H.....H...............H
H.H.............H...............................................H.....H...............H
H.H.............H...............................................H.....H...............H
H.HHHHH.....HHHHH......2........................................H.....H...............H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H...HHHHHHHHHHHHHHHHHHHHHHHHHHHHHH....................................................H
H...H............................H....................................................H
H...H............................H....................................................H
H...H..O.........................H....................................................H
H...H............................H....................................................H
H...H............................H....................................................H
H...H............................H....................................................H
H...H............................H....................................................H
H...HHHHHHHHHHHHHHHHH.....HHHHHHHH....................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
HHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHH
"""
MAP1_LANCER1_PATH = """
.......................................................................................
.......................................................................................
.....................cbavut............................................................
.....................d....s............................................................
.....................e....r............................................................
.....................f..opq............................................................
.....................g..n..............................................................
.....................h..m..............................................................
.....................ijkl..............................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
"""
MAP1_LANCER2_PATH = """
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.....................ijkl..............................................................
.....................h..m..............................................................
.....................g..n..............................................................
.....................f..opq............................................................
.....................e....r............................................................
.....................d....s............................................................
.....................cbavut............................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
.......................................................................................
"""
MAP1_LANCER_ROUTES = [MAP1_LANCER1_PATH, MAP1_LANCER2_PATH]

MAP2_NAME = "map2"
MAP2_DATA = """
HHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHH
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
H...HHHHHHHHHHHHHHHHHHHHHHHHHHHHHH....................................................H
H...H............................H....................................................H
H...H............................H....................................................H
H...H..O.........................H....................................................H
H...H............................H....................................................H
H...H............................H....................................................H
H...H............................H...............p....................................H
H...H............................H....................................................H
H...HHHHHHHHHHHHHHHHH.....HHHHHHHH....................................................H
H.....................................................................................H
H.....................................................................................H
H.....................................................................................H
HHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHHH
"""
MAP2_LANCER_ROUTES = []


if __name__ == "__main__":
    main()
