#!/usr/bin/env -S uv run python3

# TODO:
# - npcs can walk in a area (not just a path)
# - non combat npcs
# - interaction with npcs
# - multi height map
# - combine npc battles into one single battle
# - update get_pressed to use events ?
# - separate window from game logic
# - optimize drawing (only redraw changed parts)
# - multi layer render

import sys
from abc import ABC
from abc import abstractmethod
from enum import StrEnum
from enum import auto
from itertools import chain
from operator import itemgetter
from pathlib import Path
from typing import TYPE_CHECKING
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

if TYPE_CHECKING:
    from collections.abc import Iterable

type SpriteSheet = dict[Direction, dict[MovementSpeed, pygame.surface.Surface]]
type GroupKey = Literal["player", "lancer"]

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
ALERT_SPRITE_TIME = 50
ANIMATION_SPEED = 0.05


class GameWindow:
    surface: pygame.surface.Surface
    font: pygame.font.Font
    clock: pygame.time.Clock
    game_state_manager: GameStateManager
    _running: bool = True

    def __init__(self: Self) -> None:
        self.surface = pygame.display.set_mode(WINDOW_SIZE)
        self.font = pygame.font.Font(pygame.font.get_default_font())
        self.clock = pygame.time.Clock()
        self.game_state_manager = GameStateManager(game_window=self)

    def quit(self: Self) -> None:
        self._running = False

    def run(self: Self) -> None:
        self._running = True
        while self._running:
            self.run_once()
            pygame.display.flip()
            _ = self.clock.tick(FPS) / 1000

    def run_once(self: Self) -> None:
        self.dispatch()
        self.handle_events(pygame.event.get())
        self.handle_keys(pygame.key.get_pressed())
        self.update()
        self.draw()
        self.cleanup()

    def dispatch(self: Self) -> None:
        _ = self.game_state_manager.dispatch()

    def handle_events(self: Self, events: list[pygame.event.Event]) -> None:
        for event in events:
            if event.type == pygame.constants.QUIT:
                self.quit()
                return
            if event.type == pygame.constants.KEYDOWN:
                quit_keys = (pygame.constants.K_ESCAPE, pygame.constants.K_q)
                if event.key in quit_keys:  # pyright: ignore[reportAny]
                    self.quit()
                    return
        _ = self.game_state_manager.handle_events(events)

    def handle_keys(self: Self, keys: pygame.key.ScancodeWrapper) -> None:
        _ = self.game_state_manager.handle_keys(keys)

    def update(self: Self) -> None:
        _ = self.game_state_manager.update()

    def draw(self: Self) -> None:
        width, height = self.game_state_manager.map_data.get_size()
        map_rect = pygame.rect.FRect((0, 0), (width * _TILE_SIZE, height * _TILE_SIZE))
        map_surface = pygame.surface.Surface(map_rect.size)
        _ = map_surface.fill(BLACK)
        self.draw_map(map_surface)
        self.draw_debug(map_surface)
        self.draw_characters(map_surface)
        _ = self.game_state_manager.draw_on_map(map_surface)
        viewport_rect = self.surface.get_rect()
        viewport_rect.center = self.game_state_manager.player.rect.topleft
        viewport_rect.clamp_ip(map_rect)
        _ = self.surface.blit(map_surface, area=viewport_rect)
        _ = self.game_state_manager.draw_on_window(self.surface)

    def draw_map(self: Self, surface: pygame.surface.Surface) -> None:
        for (x, y), tile in self.game_state_manager.map_data.data.items():
            if tile == TileType.WALL:
                rect = pygame.rect.FRect((x * _TILE_SIZE, y * _TILE_SIZE), TILE_SIZE)
                _ = pygame.draw.rect(surface, WALL_COLOR, rect)
            elif tile == TileType.WARP:
                rect = pygame.rect.FRect((x * _TILE_SIZE, y * _TILE_SIZE), TILE_SIZE)
                _ = pygame.draw.rect(surface, FLOOR_COLOR, rect)
                _ = pygame.draw.circle(surface, BLUE, rect.center, _TILE_SIZE // 4)

    def draw_characters(self: Self, surface: pygame.surface.Surface) -> None:
        characters = [*self.game_state_manager.map_lancers, self.game_state_manager.player]
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
        for lancer in self.game_state_manager.map_lancers:
            for position in lancer.patrol_route.items:
                x, y = position
                pos = (x * _TILE_SIZE, y * _TILE_SIZE)
                rect = pygame.rect.FRect(pos, TILE_SIZE).inflate(inflate, inflate)
                if position == lancer.patrol_route.next():
                    _ = pygame.draw.rect(surface, LANCER_ROUTE_NEXT_COLOR, rect)
                else:
                    _ = pygame.draw.rect(surface, LANCER_ROUTE_COLOR, rect)

    def _draw_lancer_line_of_sight(self: Self, surface: pygame.surface.Surface) -> None:
        inflate = -_TILE_SIZE * 0.75
        for lancer in self.game_state_manager.map_lancers:
            for position in lancer.get_line_of_sight():
                x, y = position
                pos = (x * _TILE_SIZE, y * _TILE_SIZE)
                rect = pygame.rect.FRect(pos, TILE_SIZE).inflate(inflate, inflate)
                _ = pygame.draw.rect(surface, LANCER_RAYCAST_COLOR, rect, width=1)

    def cleanup(self: Self) -> None:
        _ = self.game_state_manager.cleanup()


class StateManager(ABC):
    @abstractmethod
    def is_running(self: Self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def dispatch(self: Self) -> bool:
        """Return false if event processing should stop"""
        raise NotImplementedError

    @abstractmethod
    def handle_events(self: Self, events: list[pygame.event.Event]) -> bool:
        """Return false if event processing should stop"""
        raise NotImplementedError

    @abstractmethod
    def handle_keys(self: Self, keys: pygame.key.ScancodeWrapper) -> bool:
        """Return false if event processing should stop"""
        raise NotImplementedError

    @abstractmethod
    def update(self: Self) -> bool:
        """Return false if event processing should stop"""
        raise NotImplementedError

    @abstractmethod
    def draw_on_map(self: Self, surface: pygame.surface.Surface) -> bool:
        """Return false if event processing should stop"""
        raise NotImplementedError

    @abstractmethod
    def draw_on_window(self: Self, surface: pygame.surface.Surface) -> bool:
        """Return false if event processing should stop"""
        raise NotImplementedError

    @abstractmethod
    def cleanup(self: Self) -> bool:
        """Return false if event processing should stop"""
        raise NotImplementedError


class GameStateManager(StateManager):
    game_window: GameWindow
    state: GameState
    substate_managers: list[StateManager]
    map_data: MapData
    map_lancers: list[Lancer]
    player: Player
    _map_name: str
    _map_cache: dict[MapName, MapData]
    _updating: bool

    def __init__(self: Self, game_window: GameWindow) -> None:
        self.game_window = game_window
        self.state = GameState.overworld
        self.substate_managers = []
        self.load_maps()
        self.set_map(MapName.MAP1)

    def load_maps(self: Self) -> None:
        self._map_cache = {map_name: map_name.load_map() for map_name in MapName}

    def set_map(self: Self, name: MapName) -> None:
        self._map_name = name
        self.map_data = self._map_cache[name]
        self.map_lancers = [
            Lancer(game_state_manager=self, position=position, route=route)
            for position, route in zip(
                self.map_data.lancer_positions,
                self.map_data.lancer_routes,
                strict=False,
            )
        ]
        self.player = Player(game_state_manager=self, position=self.map_data.player_position)

    @override
    def is_running(self: Self) -> bool:
        return True

    @override
    def dispatch(self: Self) -> bool:
        if self.state == GameState.game_event:
            return self.dispatch__substate_managers()
        if self.state == GameState.overworld:
            return self.dispatch__lancers()
        return True

    def dispatch__substate_managers(self: Self) -> bool:
        if not self.substate_managers:
            self.state = GameState.overworld
            return True
        for item in self.substate_managers:
            _ = item.dispatch()
            break
        return True

    def dispatch__lancers(self: Self) -> bool:
        if triggered := self.get_triggered_lancers():
            self.state = GameState.game_event
            self.substate_managers.extend(self.make_battle_start(triggered))
            return False
        for lancer in self.map_lancers:
            if lancer.is_moving:
                continue
            if lancer.state == LancerState.patrolling:
                next_position = next(lancer.patrol_route)
                if lancer.move(next_position):
                    lancer.patrol_route.advance()
        return True

    def get_triggered_lancers(self: Self) -> list[Lancer]:
        player_position = self.player.position
        if self.player.is_moving:
            player_position = self.player.next_position
        return [
            lancer
            for lancer in self.map_lancers
            if not lancer.is_moving
            and lancer.state == LancerState.patrolling
            and player_position in lancer.get_line_of_sight()
        ]

    def make_battle_start(self: Self, lancers: list[Lancer]) -> Iterable[StateManager]:
        pre_battle = chain.from_iterable(
            (
                AlertSprite(lancer),
                AlertChase(lancer, self.player),
                AlertDialog("You have been caught!", self.game_window.font),
            )
            for lancer in lancers
        )
        return [*pre_battle, Battle(self.game_window.font, lancers)]

    @override
    def handle_events(self: Self, events: list[pygame.event.Event]) -> bool:
        return True

    @override
    def handle_keys(self: Self, keys: pygame.key.ScancodeWrapper) -> bool:
        if self.state == GameState.game_event:
            return self.handle_keys__game_events(keys)
        if self.state == GameState.overworld:
            if keys[pygame.constants.K_RETURN] and not self.player.is_moving:
                self.state = GameState.game_event
                self.substate_managers.append(PauseMenu(self.game_window.font))
                return False
            return self.handle_keys__player(keys)
        return True

    def handle_keys__game_events(self: Self, keys: pygame.key.ScancodeWrapper) -> bool:
        for item in self.substate_managers:
            if not item.handle_keys(keys):
                self.substate_managers.remove(item)
            break
        return True

    def handle_keys__player(self: Self, keys: pygame.key.ScancodeWrapper) -> bool:
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
                self.player.movement_speed = MovementSpeed.RUNNING
            else:
                self.player.movement_speed = MovementSpeed.WALKING
        return True

    @override
    def update(self: Self) -> bool:
        if not self.update__game_events():
            return False
        if not self.update__lancers():
            return False
        return self.update__player()

    def update__game_events(self: Self) -> bool:
        for item in self.substate_managers:
            _ = item.update()
            break
        return True

    def update__lancers(self: Self) -> bool:
        for lancer in self.map_lancers:
            _ = lancer.update()
        return True

    def update__player(self: Self) -> bool:
        _ = self.player.update()
        return True

    @override
    def draw_on_map(self: Self, surface: pygame.surface.Surface) -> bool:
        for item in self.substate_managers:
            _ = item.draw_on_map(surface)
            break
        return True

    @override
    def draw_on_window(self: Self, surface: pygame.surface.Surface) -> bool:
        for item in self.substate_managers:
            _ = item.draw_on_window(surface)
            break
        return True

    @override
    def cleanup(self: Self) -> bool:
        for item in self.substate_managers:
            if not item.is_running():
                self.substate_managers.remove(item)
            break
        return True

    def map__can_walk(self: Self, position: pygame.typing.Point, group_key: GroupKey) -> bool:
        def get_position(character: Character) -> pygame.typing.Point:
            if character.next_position is not None:
                return character.next_position
            return character.position

        if group_key == "player" and any(position == p for p in map(get_position, self.map_lancers)):
            return False
        # XXX: add other lancers to collision check
        if group_key == "lancer" and position == get_position(self.player):
            return False
        return self.map_data.is_walkable(position)

    def map__is_warp(self: Self, position: pygame.typing.Point) -> bool:
        return self.map_data.is_warp(position)

    def character__notify_new_position(self: Self, character: Character) -> None:
        if isinstance(character, Player) and self.map__is_warp(character.position):
            if self._map_name == MapName.MAP1:
                self.set_map(MapName.MAP2)
            elif self._map_name == MapName.MAP2:
                self.set_map(MapName.MAP1)


@final
class PauseMenu(StateManager):
    surface: pygame.surface.Surface
    rect: pygame.rect.FRect
    font: pygame.font.Font
    _running: bool = True

    def __init__(self: Self, font: pygame.font.Font) -> None:
        main_window_rect = pygame.rect.FRect((0, 0), WINDOW_SIZE)
        rect = pygame.rect.FRect((0, 0), (main_window_rect.width * 0.2, main_window_rect.height * 0.8))
        self.surface = pygame.surface.Surface(rect.size)
        self.rect = rect
        self.font = font
        self.rect.midright = main_window_rect.midright
        self.rect.move_ip(-_TILE_SIZE, 0)
        self.render()

    def render(self: Self) -> None:
        _ = self.surface.fill(WHITE)
        text_surface = self.font.render("menu", antialias=True, color=BLACK)
        text_rect = text_surface.get_rect()
        text_rect.center = self.surface.get_rect().center
        border_rect = self.surface.get_rect()
        _ = self.surface.blit(text_surface, text_rect)
        _ = pygame.draw.rect(self.surface, RED, border_rect, width=1)

    def quit(self: Self) -> None:
        self._running = False

    @override
    def is_running(self: Self) -> bool:
        return self._running

    @override
    def dispatch(self: Self) -> bool:
        return True

    @override
    def handle_events(self: Self, events: list[pygame.event.Event]) -> bool:
        return True

    @override
    def handle_keys(self: Self, keys: pygame.key.ScancodeWrapper) -> bool:
        if keys[pygame.constants.K_SPACE]:
            self.quit()
        return True

    @override
    def update(self: Self) -> bool:
        return True

    @override
    def draw_on_map(self: Self, surface: pygame.surface.Surface) -> bool:
        return True

    @override
    def draw_on_window(self: Self, surface: pygame.surface.Surface) -> bool:
        _ = surface.blit(self.surface, self.rect)
        return True

    @override
    def cleanup(self: Self) -> bool:
        return True


@final
class AlertSprite(StateManager):
    _max_time: ClassVar[float] = ALERT_SPRITE_TIME
    _dt: float = 0.0
    _sprite_index: float = 0
    _sprites: list[pygame.surface.Surface]
    surface: pygame.surface.Surface
    rect: pygame.rect.FRect
    lancer: Lancer

    def __init__(self: Self, lancer: Lancer) -> None:
        sprites = _draw_alert_mark(RED)
        self.surface = sprites[0]
        self.rect = self.surface.get_frect()
        self._sprites = sprites
        self.lancer = lancer
        self.rect.midbottom = lancer.rect.midtop

    @override
    def is_running(self: Self) -> bool:
        return self._dt <= ALERT_SPRITE_TIME

    @override
    def dispatch(self: Self) -> bool:
        return True

    @override
    def handle_events(self: Self, events: list[pygame.event.Event]) -> bool:
        return True

    @override
    def handle_keys(self: Self, keys: pygame.key.ScancodeWrapper) -> bool:
        return True

    @override
    def update(self: Self) -> bool:
        self._dt += 1
        self._sprite_index = (self._sprite_index + ANIMATION_SPEED) % len(self._sprites)
        self.surface = self._sprites[int(self._sprite_index)]
        return True

    @override
    def draw_on_map(self: Self, surface: pygame.surface.Surface) -> bool:
        _ = surface.blit(self.surface, self.rect)
        return True

    @override
    def draw_on_window(self: Self, surface: pygame.surface.Surface) -> bool:
        return True

    @override
    def cleanup(self: Self) -> bool:
        return True


@final
class AlertChase(StateManager):
    lancer: Lancer
    player: Player
    _running: bool

    def __init__(self: Self, lancer: Lancer, player: Player) -> None:
        self.lancer = lancer
        self.player = player
        self._running = True

    def quit(self: Self) -> None:
        self._running = False

    @override
    def is_running(self: Self) -> bool:
        return self._running

    @override
    def dispatch(self: Self) -> bool:
        next_position = self.get_next_move()
        if self.player.position == next_position:
            self.lancer.state = LancerState.done
            self.quit()
            return False
        if not self.lancer.move(next_position):
            self.quit()
            return False
        return True

    @override
    def handle_events(self: Self, events: list[pygame.event.Event]) -> bool:
        return True

    @override
    def handle_keys(self: Self, keys: pygame.key.ScancodeWrapper) -> bool:
        return True

    @override
    def update(self: Self) -> bool:
        return True

    @override
    def draw_on_map(self: Self, surface: pygame.surface.Surface) -> bool:
        return True

    @override
    def draw_on_window(self: Self, surface: pygame.surface.Surface) -> bool:
        return True

    def get_next_move(self: Self) -> pygame.typing.Point:
        target_x, target_y = self.player.position
        x, y = self.lancer.position
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

    @override
    def cleanup(self: Self) -> bool:
        return True


@final
class AlertDialog(StateManager):
    text: str
    surface: pygame.surface.Surface
    rect: pygame.rect.FRect
    font: pygame.font.Font
    _running: bool = True

    def __init__(self: Self, text: str, font: pygame.font.Font) -> None:
        self.text = text
        main_window_rect = pygame.rect.FRect((0, 0), WINDOW_SIZE)
        rect = pygame.rect.FRect((0, 0), (main_window_rect.width * 0.8, main_window_rect.height * 0.2))
        self.surface = pygame.surface.Surface(rect.size)
        self.rect = rect
        self.font = font
        self.rect.midbottom = main_window_rect.midbottom
        self.render()

    def render(self: Self) -> None:
        _ = self.surface.fill(WHITE)
        text_surface = self.font.render(self.text, antialias=True, color=BLACK)
        text_rect = text_surface.get_rect()
        text_rect.center = self.surface.get_rect().center
        border_rect = self.surface.get_rect()
        _ = self.surface.blit(text_surface, text_rect)
        _ = pygame.draw.rect(self.surface, RED, border_rect, width=1)

    def quit(self: Self) -> None:
        self._running = False

    @override
    def is_running(self: Self) -> bool:
        return self._running

    @override
    def dispatch(self: Self) -> bool:
        return True

    @override
    def handle_events(self: Self, events: list[pygame.event.Event]) -> bool:
        return True

    @override
    def handle_keys(self: Self, keys: pygame.key.ScancodeWrapper) -> bool:
        if keys[pygame.constants.K_SPACE] or keys[pygame.constants.K_RETURN]:
            self.quit()
        return True

    @override
    def update(self: Self) -> bool:
        return True

    @override
    def draw_on_map(self: Self, surface: pygame.surface.Surface) -> bool:
        return True

    @override
    def draw_on_window(self: Self, surface: pygame.surface.Surface) -> bool:
        _ = surface.blit(self.surface, self.rect)
        return True

    @override
    def cleanup(self: Self) -> bool:
        return True


@final
class Battle(StateManager):
    surface: pygame.surface.Surface
    rect: pygame.rect.FRect
    font: pygame.font.Font
    lancers: list[Lancer]
    _running: bool = True

    def __init__(self: Self, font: pygame.font.Font, lancers: list[Lancer]) -> None:
        window_rect = pygame.rect.FRect((0, 0), WINDOW_SIZE)
        size = (window_rect.width - 2 * _TILE_SIZE, window_rect.height - 2 * _TILE_SIZE)
        rect = pygame.rect.FRect((0, 0), size)
        self.surface = pygame.surface.Surface(rect.size)
        self.rect = rect
        self.font = font
        self.rect.center = window_rect.center
        self.lancers = lancers
        self.render()

    def render(self: Self) -> None:
        _ = self.surface.fill(WHITE)
        lancer_ids = "\n".join(str(lancer.id) for lancer in self.lancers)
        text_surface = self.font.render(f"battle:\n{lancer_ids}", antialias=True, color=BLACK)
        text_rect = text_surface.get_rect()
        text_rect.center = self.surface.get_rect().center
        border_rect = self.surface.get_rect()
        _ = self.surface.blit(text_surface, text_rect)
        _ = pygame.draw.rect(self.surface, RED, border_rect, width=1)

    def quit(self: Self) -> None:
        self._running = False

    @override
    def is_running(self: Self) -> bool:
        return self._running

    @override
    def dispatch(self: Self) -> bool:
        return True

    @override
    def handle_events(self: Self, events: list[pygame.event.Event]) -> bool:
        return True

    @override
    def handle_keys(self: Self, keys: pygame.key.ScancodeWrapper) -> bool:
        if keys[pygame.constants.K_TAB]:
            self.quit()
        return True

    @override
    def update(self: Self) -> bool:
        return True

    @override
    def draw_on_map(self: Self, surface: pygame.surface.Surface) -> bool:
        return True

    @override
    def draw_on_window(self: Self, surface: pygame.surface.Surface) -> bool:
        _ = surface.blit(self.surface, self.rect)
        return True

    @override
    def cleanup(self: Self) -> bool:
        return True


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
    group_key: ClassVar[GroupKey]
    id: UUID
    game_state_manager: GameStateManager
    position: pygame.typing.Point
    surface: pygame.surface.Surface
    rect: pygame.rect.FRect
    hitbox: pygame.rect.FRect
    direction: Direction
    movement_speed: MovementSpeed
    next_position: pygame.typing.Point | None  # for grid & collision
    next_hitbox_position: pygame.typing.Point | None  # for drawing
    is_moving: bool = False
    _sprites: SpriteSheet

    def __init__(
        self: Self,
        game_state_manager: GameStateManager,
        position: pygame.typing.Point,
        sprites: SpriteSheet,
    ) -> None:
        self.id = uuid4()
        self.game_state_manager = game_state_manager
        self.position = position
        self.direction = Direction.DOWN
        self.movement_speed = MovementSpeed.WALKING
        self._sprites = sprites
        self.surface = self._sprites[self.direction][MovementSpeed.IDLE]
        self.rect = self.surface.get_frect()
        self.hitbox = pygame.rect.FRect((0, 0), TILE_SIZE)
        self.set_position(position)
        self.unset_next_position()

    def __init_subclass__(cls: type[Self], group_key: GroupKey, **kwargs: Any) -> None:  # pyright: ignore[reportAny, reportExplicitAny]  # noqa: ANN401
        super().__init_subclass__(**kwargs)
        cls.group_key = group_key

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
        if not self.game_state_manager.map__can_walk(position, group_key=self.group_key):
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
        self.surface = self._sprites[self.direction][self.movement_speed]
        if self.is_moving:
            return self.update__moving()
        return False

    def update__moving(self: Self) -> bool:
        if self.next_position is None or self.next_hitbox_position is None:
            return False
        if self.next_hitbox_position == self.hitbox.topleft:
            self.position = self.next_position
            self.unset_next_position()
            self.game_state_manager.character__notify_new_position(self)
            return False
        max_distance = self.movement_speed.speed()
        current = pygame.math.Vector2(self.hitbox.topleft)
        current.move_towards_ip(self.next_hitbox_position, max_distance)
        self.hitbox.topleft = current
        self.rect.midbottom = self.hitbox.midbottom
        return True


class Lancer(Character, group_key="lancer"):
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


class Player(Character, group_key="player"):
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


class MapName(StrEnum):
    MAP1 = auto()
    MAP2 = auto()

    def load_map(self: Self) -> MapData:
        map_filename = Path(f"{self.value.lower()}.txt")
        routes_filenames = sorted(Path().glob(f"{self.value.lower()}_lancer*.txt"))
        return MapData(map_filename=map_filename, lancer_routes_filenames=routes_filenames)


class Direction(StrEnum):
    DOWN = auto()
    UP = auto()
    RIGHT = auto()
    LEFT = auto()


class MovementSpeed(StrEnum):
    WALKING = auto()
    RUNNING = auto()
    IDLE = auto()

    def speed(self: Self) -> float:
        if self == MovementSpeed.WALKING:
            return WALKING_SPEED
        if self == MovementSpeed.RUNNING:
            return RUNNING_SPEED
        return 0.0


class TileType(StrEnum):
    EMPTY = "."
    WALL = "H"
    WARP = "O"
    LANCER = "l"
    PLAYER = "p"


class GameState(StrEnum):
    game_event = auto()
    overworld = auto()


class LancerState(StrEnum):
    patrolling = auto()
    done = auto()


def get_character_surface(color: pygame.color.Color) -> SpriteSheet:
    return {d: {m: _draw_character(d, color) for m in MovementSpeed} for d in Direction}


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


def _debug(value: str, pos: pygame.typing.Point = (10, 10)) -> None:
    global _debug_font  # noqa: PLW0603
    if _debug_font is None:
        _debug_font = pygame.font.Font(pygame.font.get_default_font())
    surface = pygame.display.get_surface()
    if surface is None:
        msg = "No display surface"
        raise RuntimeError(msg)
    text = _debug_font.render(value, antialias=True, color=WHITE, bgcolor=BLACK)
    _ = surface.blit(text, pos)


_debug_font: pygame.font.Font | None = None


def main() -> None:
    pygame.display.set_caption("The Game")
    _ = pygame.base.init()
    GameWindow().run()
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
