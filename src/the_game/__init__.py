from __future__ import annotations

import sys
from contextlib import suppress
from enum import Enum
from typing import Protocol
from typing import Self
from typing import final

import pygame
import pygame.color
import pygame.constants
import pygame.display
import pygame.draw
import pygame.event
import pygame.font
import pygame.rect
import pygame.surface
import pygame.time

WINDOW_SIZE = (960, 800)
VIEWPORT_SIZE = (800, 800)
_TILE_SIZE = 64
TILE_SIZE = (_TILE_SIZE, _TILE_SIZE)
FPS = 60
BLACK = pygame.color.Color(64, 64, 64)
WHITE = pygame.color.Color(192, 192, 192)
RED = pygame.color.Color(192, 64, 64)
GREEN = pygame.color.Color(64, 192, 64)
BLUE = pygame.color.Color(64, 64, 192)
CYAN = pygame.color.Color(64, 192, 192)
MAGENTA = pygame.color.Color(192, 64, 192)
YELLOW = pygame.color.Color(192, 192, 64)


def main() -> None:
    _ = pygame.init()
    _ = Game().main_loop()
    pygame.quit()
    sys.exit(0)


class Game:
    screen: pygame.surface.Surface
    clock: pygame.time.Clock
    font: pygame.font.Font
    ysort_camera_group: YSortCameraGroup
    hitbox_group: HitboxGroup
    player: Player
    level_world: LevelWorld

    def __init__(self: Self) -> None:
        pygame.display.set_caption("The Game")
        self.screen = pygame.display.set_mode(WINDOW_SIZE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.Font(None, size=30)
        self.ysort_camera_group = ysort_camera_group = YSortCameraGroup(items=[])
        self.hitbox_group = hitbox_group = HitboxGroup(items=[])
        self.level_world = level_world = LevelWorld()
        self.player = player = Player(pos=(128, 128))
        level_world.load_tiles([ysort_camera_group, hitbox_group])
        ysort_camera_group.add(player)

    def main_loop(self: Self) -> bool:
        while True:
            _ = self.screen.fill(BLACK)
            self.ysort_camera_group.box_target(self.player, self.level_world)
            self.ysort_camera_group.render()
            for event in pygame.event.get():
                if not (should_quit := self.handle_event(event)):
                    return should_quit
                self.player.handle_event(event)
            self.player.update([self.hitbox_group])
            _ = self.screen.blit(self.ysort_camera_group.surface)
            pygame.display.update()
            _ = self.clock.tick(FPS)

    def handle_event(self: Self, event: pygame.event.Event) -> bool:
        if event.type == pygame.constants.QUIT:
            return False
        if event.type == pygame.constants.KEYDOWN:
            if event.key == pygame.constants.K_ESCAPE:  # pyright: ignore[reportAny]
                return False
            if event.key == pygame.constants.K_q:  # pyright: ignore[reportAny]
                return False
        return True


class LevelWorld:
    rect: pygame.rect.FRect | pygame.rect.Rect
    items: dict[tuple[int, int], Tile]

    def __init__(self: Self) -> None:
        self.rect = pygame.rect.FRect((0, 0), (0, 0))
        self.items = {}

    def load_tiles(self: Self, entity_groups: list[YSortCameraGroup | HitboxGroup]) -> None:
        map_data = [list(line) for line in MAP_DATA.strip().splitlines()]
        tile_width, tile_height = TILE_SIZE
        items: dict[tuple[int, int], Tile] = {}
        for row_index, row in enumerate(map_data):
            for col_index, tile_code in enumerate(row):
                pos = (col_index * tile_width, row_index * tile_height)
                if tile_code == "x":
                    tile = Tile(pos=pos, color=CYAN)
                elif tile_code == "N":
                    tile = Tile(pos=pos, color=YELLOW)
                elif tile_code == "P":
                    tile = Tile(pos=pos, color=MAGENTA)
                else:
                    continue
                items[(col_index, row_index)] = tile
                for group in entity_groups:
                    group.add(tile)
        map_width = max(len(row) for row in map_data) * tile_width
        map_height = len(map_data) * tile_height
        self.items.update(items)
        self.rect = pygame.rect.FRect((0, 0), (map_width, map_height))


class EntityGroup[T]:
    items: list[T]

    def __init__(self: Self, items: list[T] | None = None) -> None:
        if items is None:
            items = []
        self.items = items

    def add(self: Self, item: T) -> None:
        self.items.append(item)


class IsDrawable(Protocol):
    surface: pygame.surface.Surface
    rect: pygame.rect.FRect | pygame.rect.Rect


class YSortCameraGroup(EntityGroup[IsDrawable]):
    surface: pygame.surface.Surface
    rect: pygame.rect.FRect | pygame.rect.Rect
    offset: pygame.math.Vector2
    ground_surface: pygame.surface.Surface
    ground_rect: pygame.rect.FRect | pygame.rect.Rect

    def __init__(
        self: Self,
        items: list[IsDrawable] | None = None,
        viewport_size: tuple[int, int] = VIEWPORT_SIZE,
    ) -> None:
        super().__init__(items)
        self.surface = pygame.surface.Surface(viewport_size)
        self.rect = pygame.rect.FRect((0, 0), viewport_size)
        self.offset = pygame.math.Vector2()
        self.ground_surface = ground_surface = pygame.image.load("data/graphics/tilemap/ground.png")
        self.ground_rect = ground_surface.get_rect(topleft=(0, 0))

    def box_target(self: Self, entity: Entity, level_world: LevelWorld) -> None:
        self.rect.center = entity.rect.center
        self.rect.clamp_ip(level_world.rect)
        v = pygame.math.Vector2(self.rect.left, self.rect.top)
        self.offset.update(v)

    def render(self: Self) -> None:
        _ = self.surface.fill(WHITE)
        ground_offset = self.ground_rect.topleft - self.offset
        _ = self.surface.blit(self.ground_surface, ground_offset)
        for item in sorted(self.items, key=lambda i: i.rect.centery):
            offset = item.rect.topleft - self.offset
            _ = self.surface.blit(item.surface, offset)


class HasHitbox(Protocol):
    hitbox: pygame.rect.FRect | pygame.rect.Rect


class HitboxGroup(EntityGroup[HasHitbox]): ...


class Tile:
    surface: pygame.surface.Surface
    rect: pygame.rect.FRect | pygame.rect.Rect
    hitbox: pygame.rect.FRect | pygame.rect.Rect

    def __init__(self: Self, pos: tuple[int, int], color: pygame.color.Color = RED) -> None:
        self.surface = surface = draw_rect(size=(1, 1), color=color)
        self.rect = rect = surface.get_rect(topleft=pos)
        self.hitbox = rect.inflate(0, -5)


class MovementStatus(Enum):
    UP_MOVING = "up_moving"
    UP_IDLE = "up_idle"
    DOWN_MOVING = "down_moving"
    DOWN_IDLE = "down_idle"
    LEFT_MOVING = "left_moving"
    LEFT_IDLE = "left_idle"
    RIGHT_MOVING = "right_moving"
    RIGHT_IDLE = "right_idle"


class Entity:
    surface: pygame.surface.Surface
    rect: pygame.rect.FRect | pygame.rect.Rect
    hitbox: pygame.rect.FRect | pygame.rect.Rect
    direction: pygame.math.Vector2
    movement_status: MovementStatus = MovementStatus.DOWN_IDLE
    speed: int = 5
    animations: dict[MovementStatus, list[pygame.surface.Surface]]
    _animation_frame: float = 0

    def __init__(
        self: Self,
        surface: pygame.surface.Surface,
        rect: pygame.rect.FRect | pygame.rect.Rect,
        hitbox: pygame.rect.FRect | pygame.rect.Rect | None = None,
        direction: pygame.math.Vector2 | None = None,
        speed: int = 5,
        animations: dict[MovementStatus, list[pygame.surface.Surface]] | None = None,
        _animation_frame: float = 0,
    ) -> None:
        if hitbox is None:
            hitbox = rect.copy()
        if direction is None:
            direction = pygame.math.Vector2()
        if animations is None:
            animations = {}
        self.surface = surface
        self.rect = rect
        self.hitbox = hitbox
        self.direction = direction
        self.speed = speed
        self.animations = animations
        self._animation_frame = _animation_frame

    def update_movement_status(self: Self) -> None:
        if self.direction.x > 0:
            self.movement_status = MovementStatus.RIGHT_MOVING
        elif self.direction.x < 0:
            self.movement_status = MovementStatus.LEFT_MOVING
        elif self.direction.y > 0:
            self.movement_status = MovementStatus.DOWN_MOVING
        elif self.direction.y < 0:
            self.movement_status = MovementStatus.UP_MOVING
        elif self.movement_status == MovementStatus.RIGHT_MOVING:
            self.movement_status = MovementStatus.RIGHT_IDLE
        elif self.movement_status == MovementStatus.LEFT_MOVING:
            self.movement_status = MovementStatus.LEFT_IDLE
        elif self.movement_status == MovementStatus.DOWN_MOVING:
            self.movement_status = MovementStatus.DOWN_IDLE
        elif self.movement_status == MovementStatus.UP_MOVING:
            self.movement_status = MovementStatus.UP_IDLE

    def set_animation_frame(self: Self) -> None:
        with suppress(KeyError):
            # NOTE: better adjust animation speed, based on entity speed
            frames = self.animations[self.movement_status]
            self._animation_frame = animation_frame = (self._animation_frame + 0.2) % len(frames)
            self.surface = frames[int(animation_frame)]

    def update_position(self: Self, hitbox_groups: list[HitboxGroup]) -> None:
        if (direction := self.direction).magnitude() != 0:
            direction = direction.normalize()
        self.hitbox.x += direction.x * self.speed
        for group in hitbox_groups:
            self.collision_horizontal(group)
        self.hitbox.y += direction.y * self.speed
        for group in hitbox_groups:
            self.collision_vertical(group)
        self.rect.center = self.hitbox.center

    def collision_horizontal(self: Self, hitbox_group: HitboxGroup) -> None:
        for o in hitbox_group.items:
            if o.hitbox.colliderect(self.hitbox):
                if self.direction.x > 0:  # moving right
                    self.hitbox.right = o.hitbox.left
                if self.direction.x < 0:  # moving left
                    self.hitbox.left = o.hitbox.right

    def collision_vertical(self: Self, hitbox_group: HitboxGroup) -> None:
        for o in hitbox_group.items:
            if o.hitbox.colliderect(self.hitbox):
                if self.direction.y > 0:  # moving down
                    self.hitbox.bottom = o.hitbox.top
                if self.direction.y < 0:  # moving up
                    self.hitbox.top = o.hitbox.bottom


@final
class Player(Entity):
    def __init__(self: Self, pos: tuple[int, int]) -> None:
        animations = {
            MovementStatus.UP_MOVING: [
                pygame.image.load(f"data/graphics/player/up/up_{i}.png").convert_alpha() for i in range(4)
            ],
            MovementStatus.UP_IDLE: [
                pygame.image.load("data/graphics/player/up_idle/idle_up.png").convert_alpha(),
            ],
            MovementStatus.DOWN_MOVING: [
                pygame.image.load(f"data/graphics/player/down/down_{i}.png").convert_alpha() for i in range(4)
            ],
            MovementStatus.DOWN_IDLE: [
                pygame.image.load("data/graphics/player/down_idle/idle_down.png").convert_alpha(),
            ],
            MovementStatus.LEFT_MOVING: [
                pygame.image.load(f"data/graphics/player/left/left_{i}.png").convert_alpha() for i in range(4)
            ],
            MovementStatus.LEFT_IDLE: [
                pygame.image.load("data/graphics/player/left_idle/idle_left.png").convert_alpha(),
            ],
            MovementStatus.RIGHT_MOVING: [
                pygame.image.load(f"data/graphics/player/right/right_{i}.png").convert_alpha()
                for i in range(4)
            ],
            MovementStatus.RIGHT_IDLE: [
                pygame.image.load("data/graphics/player/right_idle/idle_right.png").convert_alpha(),
            ],
        }
        surface = animations[MovementStatus.DOWN_IDLE][0]
        rect = surface.get_frect(topleft=pos)
        hitbox = rect.inflate(0, -5)
        super().__init__(surface=surface, rect=rect, hitbox=hitbox, animations=animations)

    def handle_event(self: Self, event: pygame.event.Event) -> None:  # noqa: C901
        dx, dy = self.direction
        speed = self.speed
        if event.type == pygame.constants.KEYDOWN:
            key = event.key  # pyright: ignore[reportAny]
            if key == pygame.constants.K_UP:
                dy -= 1
            if key == pygame.constants.K_DOWN:
                dy += 1
            if key == pygame.constants.K_LEFT:
                dx -= 1
            if key == pygame.constants.K_RIGHT:
                dx += 1
            if key == pygame.constants.K_LSHIFT:
                speed = 15
        if event.type == pygame.constants.KEYUP:
            key = event.key  # pyright: ignore[reportAny]
            if key == pygame.constants.K_UP:
                dy += 1
            if key == pygame.constants.K_DOWN:
                dy -= 1
            if key == pygame.constants.K_LEFT:
                dx += 1
            if key == pygame.constants.K_RIGHT:
                dx -= 1
            if key == pygame.constants.K_LSHIFT:
                speed = 5
        self.direction = pygame.math.Vector2(dx, dy)
        self.speed = speed

    def update(self: Self, hitbox_groups: list[HitboxGroup]) -> None:
        self.update_movement_status()
        self.set_animation_frame()
        self.update_position(hitbox_groups=hitbox_groups)


def draw_rect(
    size: tuple[int, int],
    color: pygame.color.Color,
) -> pygame.surface.Surface:
    tile_width, tile_height = TILE_SIZE
    width, height = size
    surface_width = width * tile_width
    surface_height = height * tile_height
    surface = pygame.surface.Surface((surface_width, surface_height))
    rect = pygame.rect.Rect((0, 0), (surface_width, surface_height))
    _ = pygame.draw.rect(surface, color, rect)
    return surface


def debug(font: pygame.font.Font, value: str) -> None:
    surface = pygame.display.get_surface()
    if surface is None:
        msg = "No display surface"
        raise RuntimeError(msg)
    text = font.render(value, antialias=True, color=WHITE, bgcolor=BLACK)
    _ = surface.blit(text, (10, 10))


MAP_DATA = """
xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
x                                                x
x                                                x
x                                                x
x                                                x
x                                                x
x     P                                    N     x
x                                                x
x                                                x
x        xxx                                     x
x        x x                                     x
x        x                                       x
x        xxx                                     x
x                                                x
x                                                x
x                                                x
x                                                x
x                                                x
x                                                x
x                                                x
x                                                x
x                                                x
x                                                x
x                                                x
x                                                x
x                                                x
x                                                x
x                                                x
x                                                x
x                                                x
x                                                x
x                                                x
x                                                x
x     N                                    N     x
x                                                x
x                                                x
x                                                x
x                                                x
x                                                x
xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
"""
