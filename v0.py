#!/usr/bin/env -S uv run python3

# TODO:
# - combine npc battles into one single battle
# - npcs can walk in a area (not just a path)
# - multi height map
# - update get_pressed to use events
# - separate window from game logic
# - optimize drawing (only redraw changed parts)
# - delegate more actions to main game loop ?

from __future__ import annotations

from enum import StrEnum
from enum import auto
from operator import itemgetter
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

FPS = 60

_TILE_SIZE = 32
TILE_SIZE = (_TILE_SIZE, _TILE_SIZE)


WALL_COLOR = WHITE
FLOOR_COLOR = BLACK
WARP_COLOR = BLUE
PLAYER_COLOR = GREEN
LANCER_COLOR = YELLOW
LANCER_CHASING_COLOR = RED
LANCER_DONE_COLOR = GREY
LANCER_PATH_COLOR = CYAN
LANCER_PATH_NEXT_COLOR = YELLOW
LANCER_RAYCAST_COLOR = MAGENTA

WALKING_SPEED = 200
RUNNING_SPEED = 500


class Window:
    surface: pygame.surface.Surface
    font: pygame.font.Font
    clock: pygame.time.Clock
    _running: bool

    def __init__(self: Self, surface: pygame.surface.Surface, font: pygame.font.Font) -> None:
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
            self.draw()
            dt = self.clock.tick(FPS) / 1000

    def handle_events(self: Self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if event.type == pygame.constants.QUIT:
                self.quit()

    def handle_keys(self: Self, keys: pygame.key.ScancodeWrapper) -> None:  # pyright: ignore[reportUnusedParameter]
        pass

    def update(self: Self, dt: float) -> bool:  # pyright: ignore[reportUnusedParameter]  # noqa: ARG002
        """Return true if event should continue to be processed"""
        return True

    def draw(self: Self) -> None:
        pass

    def quit(self: Self) -> None:
        self._running = False


class Game(Window):
    state: GameState
    map_data: MapData
    menu: Menu
    dialog: Dialog
    battle: Battle
    lancer: list[Lancer]
    player: Player
    _map_name: str
    _map_data_cache: dict[str, MapData]

    def __init__(self: Self, width: int = 960, height: int = 640) -> None:
        surface = pygame.display.set_mode((width, height))
        font = pygame.font.Font(pygame.font.get_default_font())
        pygame.display.set_caption("The Game")
        super().__init__(surface, font)
        self._map_data_cache = {
            MAP1_NAME: MapData(map_data=MAP1_DATA),
            MAP2_NAME: MapData(map_data=MAP2_DATA),
        }
        self.state = GameState.overworld
        self.menu = Menu(surface=self.surface, font=self.font)
        self.dialog = Dialog(surface=self.surface, font=self.font)
        self.battle = Battle(surface=self.surface, font=self.font)
        self.load_map(MAP1_NAME)

    def load_map(self: Self, map_name: str) -> None:
        self._map_name = map_name
        self.map_data = self._map_data_cache[map_name]
        if map_name == MAP1_NAME:
            self.lancer = [
                Lancer(game=self, position=position, path=MAP1_LANCER_PATH[i])
                for i, position in enumerate(self.map_data.lancer_positions)
            ]
        else:
            self.lancer = []
        self.player = Player(game=self, position=self.map_data.player_position)

    @override
    def handle_keys(self: Self, keys: pygame.key.ScancodeWrapper) -> None:
        if self.state == GameState.overworld:
            if keys[pygame.constants.K_ESCAPE] or keys[pygame.constants.K_q]:
                self.quit()
            elif keys[pygame.constants.K_RETURN] and self.player.movement_state != MovementState.moving:
                self.show_menu()
            else:
                self.player.handle_keys(keys)
        elif self.state == GameState.menu and keys[pygame.constants.K_RETURN]:
            self.state = GameState.overworld

    @override
    def update(self: Self, dt: float) -> bool:
        if self.state == GameState.player_found:
            return self.handle_state__player_found(dt)
        if self.state == GameState.menu:
            return self.handle_state__menu()
        if self.state == GameState.dialog:
            return self.handle_state__dialog()
        if self.state == GameState.battle:
            return self.handle_state__battle()
        if self.state == GameState.overworld:
            return self.handle_state__overworld(dt)
        return False

    def handle_state__player_found(self: Self, dt: float) -> bool:
        # XXX:
        # somehow persist cross executions:
        # npc 1 trigger, npc 1 chase, npc 1 dialog
        # npc 2 trigger, npc 2 chase, npc 2 dialog
        # duo battle
        # on dialog run, go to last state
        start_lancers = [
            lancer
            for lancer in self.lancer
            if lancer.lancer_state in (LancerState.trigger, LancerState.chase)
        ]
        battle_lancers = [lancer for lancer in self.lancer if lancer.lancer_state == LancerState.battle_start]
        if start_lancers:
            for lancer in start_lancers:
                _ = lancer.update(dt)
                break
            return True
        if battle_lancers:
            for lancer in battle_lancers:
                _ = lancer.update(dt)
                self.dialog.set_text(f"hello from {lancer.id}")
                self.dialog.run()
                lancer.lancer_state = LancerState.idle
            self.show_battle()
        return True

    def handle_state__menu(self: Self) -> bool:
        self.menu.run()
        self.state = GameState.overworld
        return True

    def handle_state__dialog(self: Self) -> bool:
        self.dialog.run()
        self.state = GameState.overworld
        return True

    def handle_state__battle(self: Self) -> bool:
        self.battle.run()
        self.state = GameState.overworld
        return True

    def handle_state__overworld(self: Self, dt: float) -> bool:
        for lancer in self.lancer:
            _ = lancer.update(dt)
        _ = self.player.update(dt)
        if self.map_data.is_warp(self.player.position):
            if self._map_name == MAP1_NAME:
                self.load_map(MAP2_NAME)
            elif self._map_name == MAP2_NAME:
                self.load_map(MAP1_NAME)
        return True

    @override
    def draw(self: Self) -> None:
        width, height = self.map_data.get_size()
        surface = pygame.surface.Surface((width * _TILE_SIZE, height * _TILE_SIZE))
        _ = surface.fill(BLACK)
        self.draw_map(surface)
        self.draw_grid(surface)
        self.draw_lancer_path(surface)
        self.draw_lancer_line_of_sight(surface)
        self.draw_characters(surface)
        self.draw_viewport(surface)
        pygame.display.flip()

    def draw_map(self: Self, surface: pygame.surface.Surface) -> None:
        for (x, y), tile in self.map_data.data.items():
            if tile == TileType.WALL:
                rect = pygame.rect.FRect((x * _TILE_SIZE, y * _TILE_SIZE), TILE_SIZE)
                _ = pygame.draw.rect(surface, WALL_COLOR, rect)
            elif tile == TileType.WARP:
                rect = pygame.rect.FRect((x * _TILE_SIZE, y * _TILE_SIZE), TILE_SIZE)
                _ = pygame.draw.rect(surface, FLOOR_COLOR, rect)
                _ = pygame.draw.circle(surface, BLUE, rect.center, _TILE_SIZE // 4)

    def draw_grid(self: Self, surface: pygame.surface.Surface) -> None:
        rect = surface.get_rect()
        for x in range(0, rect.width, _TILE_SIZE):
            _ = pygame.draw.line(surface, BLUE, (x, 0), (x, rect.height))
        for y in range(0, rect.height, _TILE_SIZE):
            _ = pygame.draw.line(surface, BLUE, (0, y), (rect.width, y))

    def draw_lancer_path(self: Self, surface: pygame.surface.Surface) -> None:
        inflate = -_TILE_SIZE * 0.75
        for lancer in self.lancer:
            for position in lancer.patrol_path.items:
                x, y = position
                pos = (x * _TILE_SIZE, y * _TILE_SIZE)
                rect = pygame.rect.FRect(pos, TILE_SIZE).inflate(inflate, inflate)
                if position == lancer.patrol_path.next():
                    _ = pygame.draw.rect(surface, LANCER_PATH_NEXT_COLOR, rect)
                else:
                    _ = pygame.draw.rect(surface, LANCER_PATH_COLOR, rect)

    def draw_lancer_line_of_sight(self: Self, surface: pygame.surface.Surface) -> None:
        inflate = -_TILE_SIZE * 0.75
        for lancer in self.lancer:
            for position in lancer.get_line_of_sight():
                x, y = position
                pos = (x * _TILE_SIZE, y * _TILE_SIZE)
                rect = pygame.rect.FRect(pos, TILE_SIZE).inflate(inflate, inflate)
                _ = pygame.draw.rect(surface, LANCER_RAYCAST_COLOR, rect, width=1)

    def draw_characters(self: Self, surface: pygame.surface.Surface) -> None:
        for lancer in self.lancer:
            _ = surface.blit(lancer.surface, lancer.rect)
        _ = surface.blit(self.player.surface, self.player.rect)

    def draw_viewport(self: Self, surface: pygame.surface.Surface) -> None:
        width, height = self.map_data.get_size()
        map_rect = pygame.rect.FRect(0, 0, width * _TILE_SIZE, height * _TILE_SIZE)
        rect = self.surface.get_frect()
        rect.center = self.player.hitbox.topleft
        rect.clamp_ip(map_rect)
        _ = self.surface.blit(surface, (0, 0), area=rect)

    def show_menu(self: Self) -> None:
        self.state = GameState.menu

    def show_dialog(self: Self) -> None:
        self.state = GameState.dialog

    def show_battle(self: Self) -> None:
        self.state = GameState.battle

    def is_walkable(
        self: Self,
        position: pygame.typing.Point,
        collision_type: Literal["player", "lancer"],
    ) -> bool:
        if collision_type == "player":
            has_collision = (
                position == p for lancer in self.lancer for p in (lancer.position, lancer.next_position)
            )
            if any(has_collision):
                return False
        if collision_type == "lancer" and position in (self.player.position, self.player.next_position):
            return False
        return self.map_data.is_walkable(position)

    def get_player_position(self: Self) -> pygame.typing.Point:
        return self.player.position


class Menu(Window):
    @override
    def draw(self: Self) -> None:
        text = self.font.render("menu", antialias=True, color=BLACK)
        size = (200, self.surface.get_height() - 40)
        surface = pygame.surface.Surface(size)
        _ = surface.fill(WHITE)
        _ = pygame.draw.rect(surface, BLACK, surface.get_rect(), width=4, border_radius=10)
        _ = surface.blit(text, (20, 20))
        rect = surface.get_rect()
        rect.midright = self.surface.get_rect().midright
        rect.move_ip(-20, 0)
        _ = self.surface.blit(surface, rect)
        pygame.display.flip()

    @override
    def handle_keys(self: Self, keys: pygame.key.ScancodeWrapper) -> None:
        if keys[pygame.constants.K_SPACE]:
            self.quit()


class Dialog(Window):
    text: str

    def __init__(
        self: Self,
        surface: pygame.surface.Surface,
        font: pygame.font.Font,
        text: str = "hello",
    ) -> None:
        self.text = text
        super().__init__(surface, font)

    @override
    def draw(self: Self) -> None:
        text = self.font.render(self.text, antialias=True, color=BLACK)
        size = (self.surface.get_width() - 40, self.surface.get_height() // 4)
        surface = pygame.surface.Surface(size)
        _ = surface.fill(WHITE)
        _ = pygame.draw.rect(surface, BLACK, surface.get_rect(), width=4, border_radius=10)
        _ = surface.blit(text, (20, 20))
        rect = surface.get_rect()
        rect.midbottom = self.surface.get_rect().midbottom
        rect.move_ip(0, -20)
        _ = self.surface.blit(surface, rect)
        pygame.display.flip()

    @override
    def handle_keys(self: Self, keys: pygame.key.ScancodeWrapper) -> None:
        if keys[pygame.constants.K_SPACE]:
            self.quit()

    def set_text(self: Self, text: str) -> None:
        self.text = text


class Battle(Window):
    @override
    def draw(self: Self) -> None:
        rect = self.surface.get_rect()
        text = self.font.render("you were caught!", antialias=True, color=BLACK)
        _ = pygame.draw.rect(self.surface, WHITE, rect.inflate(-100, -100), border_radius=10)
        _ = self.surface.blit(text, rect.move(120, 120))
        pygame.display.flip()

    @override
    def handle_keys(self: Self, keys: pygame.key.ScancodeWrapper) -> None:
        if keys[pygame.constants.K_SPACE]:
            self.quit()


class MapData:
    data: dict[pygame.typing.Point, TileType]
    lancer_positions: list[pygame.typing.Point]
    player_position: pygame.typing.Point

    def __init__(self: Self, map_data: str) -> None:
        self.data = {}
        self.lancer_positions = []
        for y, row in enumerate(map_data.strip().splitlines()):
            for x, tile in enumerate(map(TileType, row)):
                if tile in (TileType.EMPTY, TileType.WALL, TileType.WARP):
                    self.data[(x, y)] = TileType(tile)
                elif tile in (TileType.LANCER1, TileType.LANCER2):
                    self.lancer_positions.append((x, y))
                elif tile == TileType.PLAYER:
                    self.player_position = (x, y)

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
    id: UUID
    game: Game
    position: pygame.typing.Point
    surface: pygame.surface.Surface
    rect: pygame.rect.FRect
    hitbox: pygame.rect.FRect
    direction: Direction
    movement_type: MovementType
    next_position: pygame.typing.Point | None
    next_hitbox_position: pygame.typing.Point | None
    _sprites: dict[Direction, pygame.surface.Surface]
    _character_type: Literal["player", "lancer"] = "lancer"

    movement_state: MovementState

    def __init__(
        self: Self,
        game: Game,
        position: pygame.typing.Point,
        sprites: dict[Direction, pygame.surface.Surface],
    ) -> None:
        self.id = uuid4()
        self.game = game
        self._sprites = sprites
        self.surface = self._sprites[Direction.DOWN]
        self.rect = self.surface.get_frect()
        self.hitbox = pygame.rect.FRect((0, 0), TILE_SIZE)
        self.direction = Direction.DOWN
        self.movement_type = MovementType.WALKING
        self.next_position = None
        self.next_hitbox_position = None
        self.rect.midbottom = self.hitbox.midbottom
        self.movement_state = MovementState.idle
        self.set_position(position)

    def set_position(self: Self, position: pygame.typing.Point) -> None:
        self.position = position
        x, y = position
        self.hitbox.topleft = (x * _TILE_SIZE, y * _TILE_SIZE)
        self.rect.midbottom = self.hitbox.midbottom

    def set_next_position(self: Self, position: pygame.typing.Point) -> None:
        self.next_position = position
        x, y = position
        self.next_hitbox_position = (x * _TILE_SIZE, y * _TILE_SIZE)
        self.movement_state = MovementState.moving

    def move(self: Self, position: pygame.typing.Point) -> bool:
        if (direction := self.get_direction(position)) != self.direction:
            self.direction = direction
            return False
        if not self.game.is_walkable(position, self._character_type):
            return False
        self.set_next_position(position)
        return True

    def update(self: Self, dt: float) -> bool:
        if self.surface is not self._sprites[self.direction]:
            self.surface = self._sprites[self.direction]
            return False
        if self.movement_state == MovementState.moving:
            return self.handle_state__moving(dt)
        if self.movement_state == MovementState.idle:
            return self.handle_state__idle()
        return False

    def handle_state__moving(self: Self, dt: float) -> bool:
        if self.next_hitbox_position == self.hitbox.topleft:
            self.commit_position()
            return False
        return self.update_position(dt)

    def handle_state__idle(self: Self) -> bool:
        return False

    def update_position(self: Self, dt: float) -> bool:
        if self.next_hitbox_position is None:
            return False
        max_distance = self.movement_type.speed() * dt
        current = pygame.math.Vector2(self.hitbox.topleft)
        current.move_towards_ip(self.next_hitbox_position, max_distance)
        self.hitbox.topleft = current
        self.rect.midbottom = self.hitbox.midbottom
        return True

    def commit_position(self: Self) -> None:
        if self.next_position is not None:
            self.position = self.next_position
        self.next_position = None
        self.next_hitbox_position = None
        self.movement_state = MovementState.idle

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


@final
class Lancer(Character):
    lancer_state: LancerState
    line_of_sight_distance: int
    patrol_path: MovementGenerator[pygame.typing.Point]
    _normal_sprites: dict[Direction, pygame.surface.Surface]
    _angry_sprites: dict[Direction, pygame.surface.Surface]
    _tired_sprites: dict[Direction, pygame.surface.Surface]

    def __init__(
        self: Self,
        game: Game,
        position: pygame.typing.Point,
        line_of_sight_distance: int = 5,
        path: str = "",
    ) -> None:
        self._normal_sprites = {
            Direction.DOWN: _draw_direction_arrow(Direction.DOWN, LANCER_COLOR),
            Direction.UP: _draw_direction_arrow(Direction.UP, LANCER_COLOR),
            Direction.RIGHT: _draw_direction_arrow(Direction.RIGHT, LANCER_COLOR),
            Direction.LEFT: _draw_direction_arrow(Direction.LEFT, LANCER_COLOR),
        }
        self._angry_sprites = {
            Direction.DOWN: _draw_direction_arrow(Direction.DOWN, LANCER_CHASING_COLOR),
            Direction.UP: _draw_direction_arrow(Direction.UP, LANCER_CHASING_COLOR),
            Direction.RIGHT: _draw_direction_arrow(Direction.RIGHT, LANCER_CHASING_COLOR),
            Direction.LEFT: _draw_direction_arrow(Direction.LEFT, LANCER_CHASING_COLOR),
        }
        self._tired_sprites = {
            Direction.DOWN: _draw_direction_arrow(Direction.DOWN, LANCER_DONE_COLOR),
            Direction.UP: _draw_direction_arrow(Direction.UP, LANCER_DONE_COLOR),
            Direction.RIGHT: _draw_direction_arrow(Direction.RIGHT, LANCER_DONE_COLOR),
            Direction.LEFT: _draw_direction_arrow(Direction.LEFT, LANCER_DONE_COLOR),
        }
        self.lancer_state = LancerState.patrol
        self.line_of_sight_distance = line_of_sight_distance
        self.load_path(path)
        super().__init__(game, position, self._normal_sprites)

    def load_path(self: Self, path: str) -> None:
        items = [
            ((x, y), sequence)
            for y, row in enumerate(path.strip().splitlines())
            for x, sequence in enumerate(row)
            if sequence not in (".",)
        ]
        items = sorted(items, key=itemgetter(1))
        self.patrol_path = MovementGenerator([*map(itemgetter(0), items)])

    @override
    def update(self: Self, dt: float) -> bool:
        if super().update(dt):
            return True
        if self.lancer_state == LancerState.patrol:
            return self.handle_state__patrol()
        if self.lancer_state == LancerState.trigger:
            return self.handle_state__trigger()
        if self.lancer_state == LancerState.chase:
            return self.handle_state__chase()
        if self.lancer_state == LancerState.battle_start:
            return self.handle_state__battle_start()
        return False

    def handle_state__patrol(self: Self) -> bool:
        if self.game.get_player_position() in self.get_line_of_sight():
            self.game.state = GameState.player_found
            self.lancer_state = LancerState.trigger
            self._sprites = self._angry_sprites
            return True
        if self.move(next(self.patrol_path)):
            self.patrol_path.advance()
            return True
        return False

    def handle_state__trigger(self: Self) -> bool:
        self.lancer_state = LancerState.chase
        return True

    def handle_state__chase(self: Self) -> bool:
        # NOTE: use movement generator ?
        player_position = self.game.get_player_position()
        next_position = self.get_next_move(player_position)
        if player_position == next_position:
            self.lancer_state = LancerState.battle_start
            return True
        return self.move(next_position)

    def handle_state__battle_start(self: Self) -> bool:
        self._sprites = self._tired_sprites
        return True

    def get_next_move(self: Self, position: pygame.typing.Point) -> pygame.typing.Point:
        target_x, target_y = position
        x, y = self.position
        if target_y < y:  # down
            return (x, y - 1)
        if target_y > y:  # up
            return (x, y + 1)
        if target_x > x:  # right
            return (x + 1, y)
        if target_x < x:  # left
            return (x - 1, y)
        msg = "Overlapping positions"
        raise ValueError(msg)

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
            if not self.game.map_data.is_walkable(next_position):
                break
            line_of_sight.append(next_position)
        return line_of_sight


@final
class Player(Character):
    _character_type = "player"

    def __init__(
        self: Self,
        game: Game,
        position: pygame.typing.Point,
    ) -> None:
        sprites = {
            Direction.DOWN: _draw_direction_arrow(Direction.DOWN, PLAYER_COLOR),
            Direction.UP: _draw_direction_arrow(Direction.UP, PLAYER_COLOR),
            Direction.RIGHT: _draw_direction_arrow(Direction.RIGHT, PLAYER_COLOR),
            Direction.LEFT: _draw_direction_arrow(Direction.LEFT, PLAYER_COLOR),
        }
        super().__init__(game, position, sprites)

    def handle_keys(self: Self, keys: pygame.key.ScancodeWrapper) -> None:
        x, y = self.position
        if keys[pygame.constants.K_DOWN] and self.movement_state != MovementState.moving:
            _ = self.move((x, y + 1))
        elif keys[pygame.constants.K_UP] and self.movement_state != MovementState.moving:
            _ = self.move((x, y - 1))
        elif keys[pygame.constants.K_RIGHT] and self.movement_state != MovementState.moving:
            _ = self.move((x + 1, y))
        elif keys[pygame.constants.K_LEFT] and self.movement_state != MovementState.moving:
            _ = self.move((x - 1, y))
        if keys[pygame.constants.K_LSHIFT]:
            self.movement_type = MovementType.RUNNING
        else:
            self.movement_type = MovementType.WALKING


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
            msg = "No items in movement generator"
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
    menu = auto()
    dialog = auto()
    player_found = auto()
    battle = auto()


class MovementState(StrEnum):
    moving = auto()
    idle = auto()


class LancerState(StrEnum):
    patrol = auto()
    trigger = auto()
    chase = auto()
    battle_start = auto()
    idle = auto()


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
    surface.set_colorkey(BLUE)
    _ = surface.fill(BLUE)
    _ = pygame.draw.circle(surface, color, head.center, _TILE_SIZE // 4)
    _ = pygame.draw.polygon(surface, color, pody_points)
    return surface


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

MAP1_LANCER_PATH = [MAP1_LANCER1_PATH, MAP1_LANCER2_PATH]


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

MAP2_LANCER_PATH = []


def main() -> None:
    _ = pygame.base.init()
    Game().run()


if __name__ == "__main__":
    main()
