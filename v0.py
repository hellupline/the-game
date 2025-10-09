#!/usr/bin/env -S uv run python3

# TODO:
# - add map scrolling
# - add more maps
# - npcs can walk in a area (not just a path)
# - double high npc & player sprites
# - use ray casting for line of sight
# - add map transitions
# - multi height map
# - update get_pressed to use events
# - optimize drawing (only redraw changed parts)

from __future__ import annotations

from enum import Enum
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

BASE_TILE = pygame.rect.FRect((0, 0), TILE_SIZE)


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
        return True

    def draw(self: Self) -> None:
        pass

    def quit(self: Self) -> None:
        self._running = False


class Game(Window):
    game_state: GameState
    map_data: MapData
    npc: list[Lancer]
    player: Player
    menu: Menu
    dialog: Dialog

    def __init__(self: Self, width: int = 960, height: int = 640) -> None:
        surface = pygame.display.set_mode((width, height))
        font = pygame.font.Font(pygame.font.get_default_font())
        pygame.display.set_caption("The Game")
        super().__init__(surface, font)
        self.game_state = GameState.overworld
        self.map_data = MapData(map_data=MAP_DATA)
        self.npc = [
            Lancer(game=self, position=position, path=NPC_PATH[i])
            for i, position in enumerate(self.map_data.npc_positions)
        ]
        self.player = Player(game=self, position=self.map_data.player_position)
        self.menu = Menu(surface=self.surface, font=self.font)
        self.dialog = Dialog(surface=self.surface, font=self.font)

    @override
    def handle_keys(self: Self, keys: pygame.key.ScancodeWrapper) -> None:
        if self.game_state == GameState.overworld:
            if keys[pygame.constants.K_ESCAPE] or keys[pygame.constants.K_q]:
                self.quit()
            elif keys[pygame.constants.K_RETURN] and not self.player.moving:
                self.show_menu()
            else:
                self.player.handle_keys(keys)
        elif self.game_state == GameState.menu and keys[pygame.constants.K_RETURN]:
            self.game_state = GameState.overworld

    @override
    def update(self: Self, dt: float) -> bool:
        if self.game_state == GameState.npc_chasing:
            for npc in self.npc:
                _ = npc.update(dt)
            return False
        if self.game_state == GameState.dialog:
            self.dialog.run()
            self.game_state = GameState.overworld
            return False
        if self.game_state == GameState.menu:
            self.menu.run()
            self.game_state = GameState.overworld
            return False
        if self.game_state == GameState.battle:
            return False
        if self.game_state == GameState.overworld:
            for npc in self.npc:
                _ = npc.update(dt)
            _ = self.player.update(dt)
        return True

    @override
    def draw(self: Self) -> None:
        _ = self.surface.fill(BLACK)
        self.draw_map()
        self.draw_grid()
        self.draw_npc_path()
        self.draw_npc_line_of_sight()
        self.draw_characters()
        pygame.display.flip()

    def draw_map(self: Self) -> None:
        for (x, y), tile in self.map_data.data.items():
            if tile == TileType.WALL:
                _ = pygame.draw.rect(self.surface, WHITE, BASE_TILE.move(x * _TILE_SIZE, y * _TILE_SIZE))

    def draw_grid(self: Self) -> None:
        rect = self.surface.get_rect()
        for x in range(0, rect.width, _TILE_SIZE):
            _ = pygame.draw.line(self.surface, BLUE, (x, 0), (x, rect.height))
        for y in range(0, rect.height, _TILE_SIZE):
            _ = pygame.draw.line(self.surface, BLUE, (0, y), (rect.width, y))

    def draw_npc_path(self: Self) -> None:
        inflate = -_TILE_SIZE * 0.75
        for npc in self.npc:
            if npc.patrol_path is None:
                continue
            for position in npc.patrol_path.items:
                x, y = position
                pos = (x * _TILE_SIZE, y * _TILE_SIZE)
                rect = pygame.rect.FRect(pos, TILE_SIZE).inflate(inflate, inflate)
                if position == npc.patrol_path.next():
                    _ = pygame.draw.rect(self.surface, YELLOW, rect)
                else:
                    _ = pygame.draw.rect(self.surface, CYAN, rect)

    def draw_npc_line_of_sight(self: Self) -> None:
        inflate = -_TILE_SIZE * 0.75
        for npc in self.npc:
            for position in npc.get_line_of_sight():
                x, y = position
                pos = (x * _TILE_SIZE, y * _TILE_SIZE)
                rect = pygame.rect.FRect(pos, TILE_SIZE).inflate(inflate, inflate)
                _ = pygame.draw.rect(self.surface, MAGENTA, rect, width=1)

    def draw_characters(self: Self) -> None:
        for npc in self.npc:
            _ = self.surface.blit(npc.surface, npc.rect)
        _ = self.surface.blit(self.player.surface, self.player.rect)

    def is_walkable(
        self: Self,
        position: pygame.typing.Point,
        collision_type: Literal["player", "npc"],
    ) -> bool:
        if collision_type == "player":
            has_collision = (position == p for npc in self.npc for p in (npc.position, npc.next_position))
            if any(has_collision):
                return False
        if collision_type == "npc" and position in (self.player.position, self.player.next_position):
            return False
        return self.map_data.is_walkable(position)

    def get_player_position(self: Self) -> pygame.typing.Point:
        return self.player.position

    def show_menu(self: Self) -> None:
        self.game_state = GameState.menu

    def show_dialog(self: Self) -> None:
        self.game_state = GameState.dialog


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
    npc_positions: list[pygame.typing.Point]
    player_position: pygame.typing.Point

    def __init__(self: Self, map_data: str) -> None:
        self.data = {}
        self.npc_positions = []
        for y, row in enumerate(map_data.strip().splitlines()):
            for x, tile in enumerate(row):
                if tile in (".", "H"):
                    self.data[(x, y)] = TileType(tile)
                elif tile in ("1", "2"):
                    self.npc_positions.append((x, y))
                elif tile == "p":
                    self.player_position = (x, y)

    def is_walkable(self: Self, position: pygame.typing.Point) -> bool:
        return self.data.get(position) != TileType.WALL


class Character:
    id: UUID
    game: Game
    position: pygame.typing.Point
    surface: pygame.surface.Surface
    rect: pygame.rect.FRect
    direction: Direction
    movement_type: MovementType
    next_position: pygame.typing.Point | None
    next_rect_position: pygame.typing.Point | None
    moving: bool
    _sprites: dict[Direction, pygame.surface.Surface]
    _character_type: Literal["player", "npc"] = "npc"

    def __init__(
        self: Self,
        game: Game,
        position: pygame.typing.Point,
        sprites: dict[Direction, pygame.surface.Surface],
    ) -> None:
        self.id = uuid4()
        self.game = game
        self._sprites = sprites
        self.position = position
        self.surface = self._sprites[Direction.DOWN]
        x, y = position
        self.rect = BASE_TILE.move(x * _TILE_SIZE, y * _TILE_SIZE)
        self.direction = Direction.DOWN
        self.movement_type = MovementType.WALKING
        self.next_position = None
        self.next_rect_position = None
        self.moving = False

    def set_position(self: Self, position: pygame.typing.Point) -> None:
        self.position = position
        x, y = position
        self.rect.topleft = (x * _TILE_SIZE, y * _TILE_SIZE)

    def move(self: Self, position: pygame.typing.Point) -> bool:
        if self.update_direction(position):
            return False
        if not self.game.is_walkable(position, self._character_type):
            return False
        self.next_position = position
        x, y = position
        self.next_rect_position = (x * _TILE_SIZE, y * _TILE_SIZE)
        self.moving = True
        return True

    def update(self: Self, dt: float) -> bool:
        self.surface = self._sprites[self.direction]
        if self.next_rect_position == self.rect.topleft:
            self.commit_position()
            return True
        if self.next_rect_position is not None:
            self.update_position(dt)
            return True
        return False

    def update_position(self: Self, dt: float) -> None:
        if self.next_rect_position is None:
            return
        max_distance = self.movement_type.speed() * dt
        current = pygame.math.Vector2(self.rect.topleft)
        current.move_towards_ip(self.next_rect_position, max_distance)
        self.rect.topleft = current

    def commit_position(self: Self) -> None:
        if self.next_position is not None:
            self.position = self.next_position
        self.next_position = None
        self.next_rect_position = None
        self.moving = False

    def update_direction(self: Self, position: pygame.typing.Point) -> bool:
        direction = self.get_next_direction(position)
        if direction == self.direction:
            return False
        self.direction = direction
        return True

    def get_next_direction(self: Self, position: pygame.typing.Point) -> Direction:
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
class Player(Character):
    _character_type = "player"

    def __init__(
        self: Self,
        game: Game,
        position: pygame.typing.Point,
    ) -> None:
        sprites = {
            Direction.DOWN: _draw_direction_arrow(Direction.DOWN, GREEN),
            Direction.UP: _draw_direction_arrow(Direction.UP, GREEN),
            Direction.RIGHT: _draw_direction_arrow(Direction.RIGHT, GREEN),
            Direction.LEFT: _draw_direction_arrow(Direction.LEFT, GREEN),
        }
        super().__init__(game, position, sprites)

    def handle_keys(self: Self, keys: pygame.key.ScancodeWrapper) -> None:
        x, y = self.position
        if keys[pygame.constants.K_DOWN] and not self.moving:
            _ = self.move((x, y + 1))
        elif keys[pygame.constants.K_UP] and not self.moving:
            _ = self.move((x, y - 1))
        elif keys[pygame.constants.K_RIGHT] and not self.moving:
            _ = self.move((x + 1, y))
        elif keys[pygame.constants.K_LEFT] and not self.moving:
            _ = self.move((x - 1, y))
        if keys[pygame.constants.K_LSHIFT]:
            self.movement_type = MovementType.RUNNING
        else:
            self.movement_type = MovementType.WALKING


@final
class Lancer(Character):
    lancer_state: LancerState
    patrol_path: MovementGenerator[pygame.typing.Point] | None
    line_of_sight_distance: int
    _normal_sprites: dict[Direction, pygame.surface.Surface]
    _angry_sprites: dict[Direction, pygame.surface.Surface]

    def __init__(
        self: Self,
        game: Game,
        position: pygame.typing.Point,
        path: str,
        line_of_sight_distance: int = 5,
    ) -> None:
        self._normal_sprites = {
            Direction.DOWN: _draw_direction_arrow(Direction.DOWN, YELLOW),
            Direction.UP: _draw_direction_arrow(Direction.UP, YELLOW),
            Direction.RIGHT: _draw_direction_arrow(Direction.RIGHT, YELLOW),
            Direction.LEFT: _draw_direction_arrow(Direction.LEFT, YELLOW),
        }
        self._angry_sprites = {
            Direction.DOWN: _draw_direction_arrow(Direction.DOWN, RED),
            Direction.UP: _draw_direction_arrow(Direction.UP, RED),
            Direction.RIGHT: _draw_direction_arrow(Direction.RIGHT, RED),
            Direction.LEFT: _draw_direction_arrow(Direction.LEFT, RED),
        }
        self._tired_sprites = {
            Direction.DOWN: _draw_direction_arrow(Direction.DOWN, GREY),
            Direction.UP: _draw_direction_arrow(Direction.UP, GREY),
            Direction.RIGHT: _draw_direction_arrow(Direction.RIGHT, GREY),
            Direction.LEFT: _draw_direction_arrow(Direction.LEFT, GREY),
        }
        self.lancer_state = LancerState.patrolling
        self.patrol_path = MovementGenerator(self.load_path(path))
        self.line_of_sight_distance = line_of_sight_distance
        super().__init__(game, position, self._normal_sprites)

    def load_path(self: Self, path: str) -> list[pygame.typing.Point]:
        items = [
            ((x, y), sequence)
            for y, row in enumerate(path.strip().splitlines())
            for x, sequence in enumerate(row)
            if sequence not in (".",)
        ]
        items = sorted(items, key=itemgetter(1))
        return [*map(itemgetter(0), items)]

    @override
    def update(self: Self, dt: float) -> bool:
        if super().update(dt):
            return True
        return self.update_patrol()

    def update_patrol(self: Self) -> bool:
        player_position = self.game.get_player_position()
        if self.lancer_state == LancerState.patrolling:
            if player_position in self.get_line_of_sight():
                self.game.game_state = GameState.npc_chasing
                self.lancer_state = LancerState.chasing
                self._sprites = self._angry_sprites
                return True
            if self.patrol_path is not None and self.move(next(self.patrol_path)):
                self.patrol_path.advance()
                return True
        elif self.lancer_state == LancerState.chasing:
            next_position = self.get_next_move(player_position)
            if next_position == player_position:
                self.game.game_state = GameState.overworld
                self.lancer_state = LancerState.idle
                self.game.show_dialog()
                self._sprites = self._tired_sprites
                return True
            return self.move(next_position)
        return False

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
        # XXX: update to use ray casting
        x, y = self.position
        if self.direction == Direction.DOWN:
            return [(x, y + i) for i in range(1, self.line_of_sight_distance + 1)]
        if self.direction == Direction.UP:
            return [(x, y - i) for i in range(1, self.line_of_sight_distance + 1)]
        if self.direction == Direction.RIGHT:
            return [(x + i, y) for i in range(1, self.line_of_sight_distance + 1)]
        if self.direction == Direction.LEFT:
            return [(x - i, y) for i in range(1, self.line_of_sight_distance + 1)]
        msg = "Invalid direction"
        raise ValueError(msg)


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


class Direction(Enum):
    DOWN = "down"
    UP = "up"
    RIGHT = "right"
    LEFT = "left"


class MovementType(Enum):
    IDLE = "idle"
    WALKING = "walking"
    RUNNING = "running"

    def speed(self: Self) -> float:
        if self == MovementType.WALKING:
            return 200.0
        if self == MovementType.RUNNING:
            return 400.0
        return 0.0


class TileType(Enum):
    EMPTY = "."
    WALL = "H"
    NPC1 = "1"
    NPC2 = "2"
    PLAYER = "p"


class GameState(Enum):
    overworld = "overworld"
    menu = "menu"
    dialog = "dialog"
    npc_chasing = "npc_chasing"
    battle = "battle"


class LancerState(Enum):
    idle = "idle"
    patrolling = "patrolling"
    chasing = "chasing"


def _draw_direction_arrow(direction: Direction, color: pygame.color.Color) -> pygame.surface.Surface:
    if direction == Direction.DOWN:
        points = [BASE_TILE.topleft, BASE_TILE.topright, BASE_TILE.midbottom, BASE_TILE.topleft]
    elif direction == Direction.UP:
        points = [BASE_TILE.bottomleft, BASE_TILE.bottomright, BASE_TILE.midtop, BASE_TILE.bottomleft]
    elif direction == Direction.RIGHT:
        points = [BASE_TILE.topleft, BASE_TILE.bottomleft, BASE_TILE.midright, BASE_TILE.topleft]
    elif direction == Direction.LEFT:
        points = [BASE_TILE.topright, BASE_TILE.bottomright, BASE_TILE.midleft, BASE_TILE.topright]
    surface = pygame.surface.Surface((_TILE_SIZE, _TILE_SIZE))
    surface.set_colorkey(BLUE)
    _ = surface.fill(BLUE)
    _ = pygame.draw.polygon(surface, color, points)
    return surface


def main() -> None:
    _ = pygame.base.init()
    Game().run()


MAP_DATA = """
HHHHHHHHHHHHHHHHHHHHHHHHHHHHHH
H............................H
H.HHHHH.....HHHHH......1.....H
H.H.............H............H
H.H.............H............H
H.H.............H............H
H.H...HHHHHHH...H............H
H.....HHHHHHH................H
H.....HHHHHHH................H
H.....HHHHHHH.............p..H
H.....HHHHHHH................H
H.....HHHHHHH................H
H.H...HHHHHHH...H............H
H.H.............H............H
H.H.............H............H
H.H.............H............H
H.HHHHH.....HHHHH......2.....H
H............................H
H............................H
HHHHHHHHHHHHHHHHHHHHHHHHHHHHHH
"""

NPC_PATH1 = """
..............................
..............................
.....................cbavut...
.....................d....s...
.....................e....r...
.....................f..opq...
.....................g..n.....
.....................h..m.....
.....................ijkl.....
..............................
..............................
..............................
..............................
..............................
..............................
..............................
..............................
..............................
..............................
..............................
"""

NPC_PATH2 = """
..............................
..............................
..............................
..............................
..............................
..............................
..............................
..............................
..............................
..............................
.....................ijkl.....
.....................h..m.....
.....................g..n.....
.....................f..opq...
.....................e....r...
.....................d....s...
.....................cbavut...
..............................
..............................
..............................
"""

NPC_PATH = [NPC_PATH1, NPC_PATH2]


if __name__ == "__main__":
    main()
