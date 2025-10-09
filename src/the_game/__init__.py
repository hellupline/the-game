from __future__ import annotations

import sys
from contextlib import suppress
from csv import reader
from enum import Enum
from enum import IntEnum
from functools import cached_property
from io import StringIO
from itertools import chain
from pathlib import Path
from typing import TYPE_CHECKING
from typing import Literal
from typing import Self
from typing import TypedDict
from typing import final
from typing import override

import pygame
import pygame.color
import pygame.constants
import pygame.display
import pygame.event
import pygame.font
import pygame.surface
import pygame.time
from defusedxml.ElementTree import parse as xml_parse

if TYPE_CHECKING:
    from collections.abc import Iterable
    from collections.abc import Iterator
    from collections.abc import Sequence
    from xml.etree.ElementTree import Element

    from pygame.typing import Point

BLACK = pygame.color.Color(64, 64, 64)
WHITE = pygame.color.Color(240, 240, 240)
RED = pygame.color.Color(240, 64, 64)
GREEN = pygame.color.Color(64, 240, 64)
BLUE = pygame.color.Color(64, 64, 240)
CYAN = pygame.color.Color(64, 240, 240)
MAGENTA = pygame.color.Color(240, 64, 240)
YELLOW = pygame.color.Color(240, 240, 64)

_WINDOW_WIDTH = 15  # how many tiles horizontally
_WINDOW_HEIGHT = 10  # how many tiles vertically
_TILE_SIZE = 16
_SCALE_FACTOR = 3
WINDOW_SIZE = (_WINDOW_WIDTH * _TILE_SIZE * _SCALE_FACTOR, _WINDOW_HEIGHT * _TILE_SIZE * _SCALE_FACTOR)
VIEWPORT_SIZE = (_WINDOW_WIDTH * _TILE_SIZE, _WINDOW_HEIGHT * _TILE_SIZE)
TILE_SIZE = (_TILE_SIZE, _TILE_SIZE)
FPS = 60

MAPS_DIR = Path("data/maps")
PLAYER_COLORKEY = pygame.color.Color(255, 127, 39)
PLAYER_SPRITE_FILENAME = Path("data/sprites/player.png")

MOVEMENT_SPEED_WALKING = 60
MOVEMENT_SPEED_RUNNING = 180
ANIMATION_SPEED = 5


class Assets(TypedDict):
    map_1: TiledMap
    map_2: TiledMap
    player_sprites: dict[tuple[MovementDirection, MovementStatus], list[pygame.surface.Surface]]


class MovementDirection(Enum):
    DOWN = "down"
    UP = "up"
    RIGHT = "right"
    LEFT = "left"


class MovementStatus(Enum):
    IDLE = "idle"
    WALKING = "walking"
    RUNNING = "running"

    def get_movement_speed(self: Self) -> int:
        if self == MovementStatus.RUNNING:
            return MOVEMENT_SPEED_RUNNING
        if self == MovementStatus.WALKING:
            return MOVEMENT_SPEED_WALKING
        return 0


class SpriteLayer(IntEnum):
    BACKGROUND = 0
    MAIN = 1


class Game:
    surface: pygame.surface.Surface
    clock: pygame.time.Clock
    camera: Camera
    player: Player
    collision_group: CollisionGroup
    entities: list[Entity]
    warps: dict[str, Warps]
    _assets: Assets

    def __init__(self: Self) -> None:
        pygame.display.set_caption("The Game")
        self.surface = pygame.display.set_mode(WINDOW_SIZE)
        self.clock = pygame.time.Clock()
        self.camera = Camera()
        self.collision_group = CollisionGroup()
        self.entities = []
        self.warps = {}
        self.load_assets()
        self.init_map("map_1", "warp-targets", "target_1")

    def load_assets(self: Self) -> None:
        self._assets = {
            "map_1": TiledMap(MAPS_DIR / "map_1.tmx"),
            "map_2": TiledMap(MAPS_DIR / "map_2.tmx"),
            "player_sprites": load_player_sprites(),
        }

    def init_map(
        self: Self,
        name: Literal["map_1", "map_2"],
        object_group: str,
        object_name: str,
    ) -> None:
        self.camera.clear()
        self.collision_group.clear()
        self.entities.clear()
        tiled_map = self._assets[name]
        for x, y, surface in tiled_map.get_layer("background").tiles():
            tile = Tile(
                position=(x, y),
                surface=surface,
                layer=SpriteLayer.BACKGROUND,
            )
            self.camera.append(tile)
        for obj in tiled_map.get_object_group("walls"):
            self.collision_group.append(obj.rect)
        for obj in tiled_map.get_object_group("warps"):
            if obj.name is None:
                continue
            self.warps[obj.name] = Warps(position=obj.position)
        obj = tiled_map.get_object_group(object_group).get_object(object_name)
        self.player = Player(
            position=obj.position,
            surface=self._assets["player_sprites"][(MovementDirection.DOWN, MovementStatus.IDLE)][0],
            layer=SpriteLayer.MAIN,
            collision_group=self.collision_group,
            animations=self._assets["player_sprites"],
        )
        self.camera.append(self.player)
        self.entities.append(self.player)

    def run(self: Self) -> None:
        dt = 0
        while True:
            for event in pygame.event.get():
                self.handle_event(event)
            self.player.get_input()
            for entity in self.entities:
                entity.update(dt)
            self.draw()
            if not self.player.moving:
                for name, warp in self.warps.items():
                    if warp.rect == self.player.hitbox:
                        if name == "warp_2":
                            self.init_map("map_2", "warp-targets", "target_1")
            dt = self.clock.tick(FPS) / 1000

    def handle_event(self: Self, event: pygame.event.Event) -> None:
        if event.type == pygame.constants.QUIT:
            pygame.quit()
            sys.exit(0)
        if event.type == pygame.constants.KEYDOWN:
            if event.key == pygame.constants.K_ESCAPE:  # pyright: ignore[reportAny]
                pygame.quit()
                sys.exit(0)
            if event.key == pygame.constants.K_q:  # pyright: ignore[reportAny]
                pygame.quit()
                sys.exit(0)

    def draw(self: Self) -> None:
        self.camera.box_target(self.player)
        self.camera.draw()
        _ = self.surface.fill(BLACK)
        _ = pygame.transform.scale_by(
            self.camera.surface,
            factor=_SCALE_FACTOR,
            dest_surface=self.surface,
        )
        pygame.display.update()


class Camera:
    items: list[Tile | Entity]
    surface: pygame.surface.Surface
    rect: pygame.rect.FRect
    offset: pygame.math.Vector2
    _area_rect: pygame.rect.FRect | None = None

    def __init__(self: Self, size: Point = VIEWPORT_SIZE) -> None:
        self.items = []
        self.surface = pygame.surface.Surface(size)
        self.rect = self.surface.get_frect()
        self.offset = pygame.math.Vector2()

    def append(self: Self, item: Tile | Entity) -> None:
        self.items.append(item)
        self._area_rect = None

    def extend(self: Self, item: list[Tile | Entity]) -> None:
        self.items.extend(item)
        self._area_rect = None

    def remove(self: Self, item: Tile | Entity) -> None:
        self.items.remove(item)
        self._area_rect = None

    def clear(self: Self) -> None:
        self.items.clear()
        self._area_rect = None

    @cached_property
    def min_area_rect(self: Self) -> pygame.rect.FRect:
        if self._area_rect is None:
            self._area_rect = get_min_area([tile.rect for tile in self.items])
        return self._area_rect

    def box_target(self: Self, entity: Entity) -> None:
        self.rect.center = entity.rect.center
        self.rect.clamp_ip(self.min_area_rect)
        self.offset.update(self.rect.topleft)

    def draw(self: Self) -> None:
        _ = self.surface.fill(BLACK)
        items = self.items
        items = sorted(items, key=lambda item: (item.layer, item.y_sort))
        _ = self.surface.blits((item.surface, item.rect.move(-self.offset)) for item in items)
        draw_grid(self.surface, offset=-self.offset)


class CollisionGroup:
    items: list[pygame.rect.FRect]

    def __init__(self: Self) -> None:
        self.items = []

    def append(self: Self, item: pygame.rect.FRect) -> None:
        self.items.append(item)

    def extend(self: Self, item: list[pygame.rect.FRect]) -> None:
        self.items.extend(item)

    def remove(self: Self, item: pygame.rect.FRect) -> None:
        self.items.remove(item)

    def clear(self: Self) -> None:
        self.items.clear()


class Tile:
    surface: pygame.surface.Surface
    rect: pygame.rect.FRect
    layer: SpriteLayer = SpriteLayer.BACKGROUND

    def __init__(
        self: Self,
        position: Point = (0, 0),
        surface: pygame.surface.Surface | None = None,
        layer: SpriteLayer = SpriteLayer.BACKGROUND,
    ) -> None:
        if surface is None:
            surface = pygame.surface.Surface(TILE_SIZE)
            _ = surface.fill(MAGENTA)
        self.surface = surface
        self.rect = surface.get_frect(topleft=position)
        self.layer = layer

    def update(self: Self, dt: float) -> None:  # pyright: ignore[reportUnusedParameter]
        pass

    @property
    def y_sort(self: Self) -> float:
        return self.rect.centery


class Entity(Tile):
    surface: pygame.surface.Surface
    hitbox: pygame.rect.FRect
    movement_vector: pygame.math.Vector2
    movement_direction: MovementDirection
    movement_status: MovementStatus
    moving: bool = False
    collision_group: CollisionGroup | None
    animations: dict[tuple[MovementDirection, MovementStatus], list[pygame.surface.Surface]]
    _animation_index: float = 0  # XXX: animation interruption

    def __init__(
        self: Self,
        position: Point = (0, 0),
        surface: pygame.surface.Surface | None = None,
        movement_vector: pygame.math.Vector2 | None = None,
        movement_direction: MovementDirection = MovementDirection.DOWN,
        movement_status: MovementStatus = MovementStatus.IDLE,
        layer: SpriteLayer = SpriteLayer.MAIN,
        collision_group: CollisionGroup | None = None,
        animations: dict[tuple[MovementDirection, MovementStatus], list[pygame.surface.Surface]]
        | None = None,
    ) -> None:
        super().__init__(position=position, surface=surface, layer=layer)
        if movement_vector is None:
            movement_vector = pygame.math.Vector2(0, 0)
        if animations is None:
            animations = {}
        self.movement_vector = movement_vector
        self.movement_direction = movement_direction
        self.movement_status = movement_status
        self.collision_group = collision_group
        self.animations = animations
        # XXX: better handle hitbox shape/size/anchor
        self.hitbox = pygame.rect.FRect(position, (_TILE_SIZE, _TILE_SIZE))
        self.rect.bottomleft = self.hitbox.bottomleft

    def move_down(self: Self, run: bool = False) -> None:  # noqa: FBT001, FBT002
        self._move(MovementDirection.DOWN, pygame.math.Vector2(0, _TILE_SIZE), run)

    def move_up(self: Self, run: bool = False) -> None:  # noqa: FBT001, FBT002
        self._move(MovementDirection.UP, pygame.math.Vector2(0, -_TILE_SIZE), run)

    def move_right(self: Self, run: bool = False) -> None:  # noqa: FBT001, FBT002
        self._move(MovementDirection.RIGHT, pygame.math.Vector2(_TILE_SIZE, 0), run)

    def move_left(self: Self, run: bool = False) -> None:  # noqa: FBT001, FBT002
        self._move(MovementDirection.LEFT, pygame.math.Vector2(-_TILE_SIZE, 0), run)

    def _move(
        self: Self,
        direction: MovementDirection,
        vector: pygame.math.Vector2,
        run: bool = False,  # noqa: FBT001, FBT002
    ) -> None:
        # XXX: implement throttle here; if running, bypass throttle
        if self.movement_direction != direction:
            self.movement_direction = direction
            return
        self.movement_vector = self.hitbox.topleft + vector
        if run:
            self.movement_status = MovementStatus.RUNNING
        else:
            self.movement_status = MovementStatus.WALKING
        self.moving = True

    def move_stop(self: Self) -> None:
        self.moving = False
        self.movement_vector = pygame.math.Vector2()
        self.movement_status = MovementStatus.IDLE

    @override
    def update(self: Self, dt: float) -> None:
        self.set_animation_frame(dt)
        self.update_position(dt)

    def set_animation_frame(self: Self, dt: float) -> None:
        with suppress(KeyError):
            frames = self.animations[(self.movement_direction, self.movement_status)]
            self._animation_index = (self._animation_index + ANIMATION_SPEED * dt) % len(frames)
            self.surface = frames[int(self._animation_index)]

    def update_position(self: Self, dt: float) -> None:
        if self.movement_vector.magnitude() == 0:
            return
        movement_speed = round(self.movement_status.get_movement_speed() * dt)
        pos = pygame.math.Vector2(self.hitbox.topleft)
        pos.move_towards_ip(self.movement_vector, movement_speed)
        if pos == self.movement_vector:
            self.move_stop()
        rect = self.hitbox.copy()
        rect.topleft = pos
        if self.collision_test(rect):
            self.move_stop()
            return
        self.hitbox.topleft = rect.topleft
        self.rect.bottomleft = self.hitbox.bottomleft

    def collision_test(self: Self, rect: pygame.rect.FRect) -> bool:
        if not self.collision_group:
            return False
        for item in self.collision_group.items:
            if not item.colliderect(rect):
                continue
            if self.movement_direction == MovementDirection.DOWN:
                rect.bottom = item.top
            elif self.movement_direction == MovementDirection.UP:
                rect.top = item.bottom
            elif self.movement_direction == MovementDirection.RIGHT:
                rect.right = item.left
            elif self.movement_direction == MovementDirection.LEFT:
                rect.left = item.right
            return True
        return False


@final
class Player(Entity):
    def get_input(self: Self) -> None:
        if self.moving:
            return
        keys = pygame.key.get_pressed()
        keys_down = keys[pygame.constants.K_DOWN] or keys[pygame.constants.K_s]
        keys_up = keys[pygame.constants.K_UP] or keys[pygame.constants.K_w]
        keys_right = keys[pygame.constants.K_RIGHT] or keys[pygame.constants.K_d]
        keys_left = keys[pygame.constants.K_LEFT] or keys[pygame.constants.K_a]
        keys_run = keys[pygame.constants.K_LSHIFT] or keys[pygame.constants.K_RSHIFT]
        if keys_down:
            self.move_down(run=keys_run)
            return
        if keys_up:
            self.move_up(run=keys_run)
            return
        if keys_right:
            self.move_right(run=keys_run)
            return
        if keys_left:
            self.move_left(run=keys_run)
            return


class Warps:
    rect: pygame.rect.FRect

    def __init__(self: Self, position: Point) -> None:
        self.rect = pygame.rect.FRect(position, TILE_SIZE)


class TiledMap:
    layers: list[TiledTileLayer]
    layers_by_name: dict[str, TiledTileLayer]
    layers_by_id: dict[int, TiledTileLayer]
    object_groups: list[TiledObjectGroup]
    object_groups_by_name: dict[str, TiledObjectGroup]
    object_groups_by_id: dict[int, TiledObjectGroup]
    tilesets: list[TiledTileset]
    tilesets_by_name: dict[str, TiledTileset]
    width: int
    height: int
    tilewidth: int
    tileheight: int
    filename: Path

    def __init__(self: Self, filename: Path) -> None:
        root = xml_parse(filename).getroot()
        if root is None:
            msg = f"Failed to parse TMX file: {filename}"
            raise ValueError(msg)
        self.filename = filename
        self.width = int(root.attrib["width"])
        self.height = int(root.attrib["height"])
        self.tilewidth = int(root.attrib["tilewidth"])
        self.tileheight = int(root.attrib["tileheight"])
        self.layers = [TiledTileLayer(el, self) for el in root.findall("layer")]
        self.layers_by_name = {t.name: t for t in self.layers}
        self.layers_by_id = {t.id: t for t in self.layers}
        self.object_groups = [TiledObjectGroup(el, self) for el in root.findall("objectgroup")]
        self.object_groups_by_name = {t.name: t for t in self.object_groups}
        self.object_groups_by_id = {t.id: t for t in self.object_groups}
        self.tilesets = [TiledTileset(el, self) for el in root.findall("tileset")]
        self.tilesets_by_name = {t.name: t for t in self.tilesets}

    def get_layer(self: Self, key: str | int) -> TiledTileLayer:
        if isinstance(key, str):
            return self.layers_by_name[key]
        return self.layers_by_id[key]

    def get_object_group(self: Self, key: str | int) -> TiledObjectGroup:
        if isinstance(key, str):
            return self.object_groups_by_name[key]
        return self.object_groups_by_id[key]

    def get_tile(self: Self, gid: str) -> pygame.surface.Surface:
        for tileset in self.tilesets:
            if int(gid) < tileset.firstgid:
                continue
            try:
                return tileset[gid]
            except KeyError:
                break
        msg = f"Tile GID {gid} not found in any tileset"
        raise KeyError(msg)


class TiledTileLayer:
    _parent: TiledMap
    data: list[tuple[str]]
    name: str
    id: int
    width: int
    height: int

    def __init__(self: Self, node: Element, parent: TiledMap) -> None:
        data_node = node.find("data")
        if data_node is None or data_node.text is None:
            msg = f"Layer {self.name} has no data"
            raise ValueError(msg)
        self._parent = parent
        self.name = node.attrib["name"]
        self.id = int(node.attrib["id"])
        self.width = int(node.attrib["width"])
        self.height = int(node.attrib["height"])
        self.data = load_tiles_data(data_node.text, self.width)

    def __iter__(self: Self) -> Iterator[tuple[int, int, str]]:
        tilewidth, tileheight = self._parent.tilewidth, self._parent.tileheight
        for y, row in enumerate(self.data):
            for x, gid in enumerate(row):
                yield (x * tilewidth, y * tileheight, gid)

    def tiles(self: Self) -> Iterator[tuple[int, int, pygame.surface.Surface]]:
        for x, y, gid in self:
            yield (x, y, self._parent.get_tile(gid))


class TiledObjectGroup:
    _parent: TiledMap
    objects: list[TiledObject]
    objects_by_name: dict[str, TiledObject]
    objects_by_id: dict[int, TiledObject]
    name: str
    id: int
    visible: bool
    locked: bool

    def __init__(self: Self, node: Element, parent: TiledMap) -> None:
        self._parent = parent
        self.name = node.attrib["name"]
        self.id = int(node.attrib["id"])
        self.visible = parse_bool(node.attrib.get("visible", "1"))
        self.locked = parse_bool(node.attrib.get("locked", "0"))
        self.objects = [TiledObject(el, self) for el in node.findall("object")]
        self.objects_by_name = {t.name: t for t in self.objects if t.name is not None}
        self.objects_by_id = {t.id: t for t in self.objects}

    def __iter__(self: Self) -> Iterator[TiledObject]:
        return iter(self.objects)

    def __getitem__(self: Self, key: str | int) -> TiledObject:
        if isinstance(key, str):
            return self.objects_by_name[key]
        return self.objects_by_id[key]

    def get_object(self: Self, key: str | int) -> TiledObject:
        return self[key]


class TiledObject:
    _parent: TiledObjectGroup
    name: str | None
    id: int
    x: float
    y: float
    width: float
    height: float

    def __init__(self: Self, node: Element, parent: TiledObjectGroup) -> None:
        self._parent = parent
        self.name = node.attrib.get("name")
        self.id = int(node.attrib["id"])
        self.x = float(node.attrib["x"])
        self.y = float(node.attrib["y"])
        self.width = float(node.attrib["width"])
        self.height = float(node.attrib["height"])

    @cached_property
    def rect(self: Self) -> pygame.rect.FRect:
        return pygame.rect.FRect(self.x, self.y, self.width, self.height)

    @property
    def position(self: Self) -> Point:
        return (self.x, self.y)

    @property
    def size(self: Self) -> Point:
        return (self.width, self.height)


class TiledTileset:
    _parent: TiledMap
    tiles: dict[str, pygame.surface.Surface]
    firstgid: int
    source: Path
    name: str
    tilewidth: int
    tileheight: int
    tilecount: int
    columns: int
    image_width: int
    image_height: int
    image_source: Path

    def __init__(self: Self, node: Element, parent: TiledMap) -> None:
        source = parent.filename.parent / node.attrib["source"]
        root = xml_parse(source).getroot()
        if root is None:
            msg = f"Failed to parse TSX file: {self.source}"
            raise ValueError(msg)
        self._parent = parent
        self.firstgid = int(node.attrib["firstgid"])
        self.source = source
        self.name = root.attrib["name"]
        self.tilewidth = int(root.attrib["tilewidth"])
        self.tileheight = int(root.attrib["tileheight"])
        self.tilecount = int(root.attrib["tilecount"])
        self.columns = int(root.attrib["columns"])
        image_node = root.find("image")
        if image_node is None:
            msg = f"Tileset {self.name} has no image"
            raise ValueError(msg)
        self.image_source = source.parent / image_node.attrib["source"]
        self.image_width = int(image_node.attrib["width"])
        self.image_height = int(image_node.attrib["height"])
        self.tiles = self.load_tiles()

    def load_tiles(self: Self) -> dict[str, pygame.surface.Surface]:
        surface = pygame.image.load(self.image_source).convert_alpha()
        tiles: list[pygame.surface.Surface] = []
        for y in range(0, self.image_height, self.tileheight):
            for x in range(0, self.image_width, self.tilewidth):
                rect = pygame.FRect((x, y), (self.tilewidth, self.tileheight))
                tile = surface.subsurface(rect)
                tiles.append(tile)
        return {str(i): tile for i, tile in enumerate(tiles, start=self.firstgid)}

    def __getitem__(self: Self, gid: str) -> pygame.surface.Surface:
        return self.tiles[gid]


def load_tiles_data(value: str, width: int) -> list[tuple[str]]:
    buf = StringIO(value.replace("\n", ""))
    items = map(str.strip, chain.from_iterable(reader(buf)))
    return reshape(items, width)


def reshape[T](items: Iterable[T], n: int) -> list[tuple[T]]:
    iterators = [items] * n
    return [*zip(*iterators, strict=True)]


def parse_bool(value: str) -> bool:
    value = value.strip().lower()
    if value in ("1", "true", "yes"):
        return True
    if value in ("0", "false", "no"):
        return False
    msg = f"Invalid boolean value: {value}"
    raise ValueError(msg)


def load_player_sprites() -> dict[tuple[MovementDirection, MovementStatus], list[pygame.surface.Surface]]:
    image = pygame.image.load(PLAYER_SPRITE_FILENAME).convert_alpha()
    image.set_colorkey(PLAYER_COLORKEY)
    tile_width, tile_height = 16, 32
    return {
        (MovementDirection.DOWN, MovementStatus.IDLE): [
            image.subsurface(pygame.rect.FRect(1 * tile_width, 0 * tile_height, tile_width, tile_height)),
        ],
        (MovementDirection.UP, MovementStatus.IDLE): [
            image.subsurface(pygame.rect.FRect(1 * tile_width, 1 * tile_height, tile_width, tile_height)),
        ],
        (MovementDirection.LEFT, MovementStatus.IDLE): [
            image.subsurface(pygame.rect.FRect(1 * tile_width, 2 * tile_height, tile_width, tile_height)),
        ],
        (MovementDirection.RIGHT, MovementStatus.IDLE): [
            image.subsurface(pygame.rect.FRect(1 * tile_width, 3 * tile_height, tile_width, tile_height)),
        ],
        (MovementDirection.DOWN, MovementStatus.WALKING): [
            image.subsurface(pygame.rect.FRect(0 * tile_width, 0 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(1 * tile_width, 0 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(2 * tile_width, 0 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(1 * tile_width, 0 * tile_height, tile_width, tile_height)),
        ],
        (MovementDirection.UP, MovementStatus.WALKING): [
            image.subsurface(pygame.rect.FRect(0 * tile_width, 1 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(1 * tile_width, 1 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(2 * tile_width, 1 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(1 * tile_width, 1 * tile_height, tile_width, tile_height)),
        ],
        (MovementDirection.LEFT, MovementStatus.WALKING): [
            image.subsurface(pygame.rect.FRect(0 * tile_width, 2 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(1 * tile_width, 2 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(2 * tile_width, 2 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(1 * tile_width, 2 * tile_height, tile_width, tile_height)),
        ],
        (MovementDirection.RIGHT, MovementStatus.WALKING): [
            image.subsurface(pygame.rect.FRect(0 * tile_width, 3 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(1 * tile_width, 3 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(2 * tile_width, 3 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(1 * tile_width, 3 * tile_height, tile_width, tile_height)),
        ],
        (MovementDirection.DOWN, MovementStatus.RUNNING): [
            image.subsurface(pygame.rect.FRect(3 * tile_width, 0 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(4 * tile_width, 0 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(5 * tile_width, 0 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(4 * tile_width, 0 * tile_height, tile_width, tile_height)),
        ],
        (MovementDirection.UP, MovementStatus.RUNNING): [
            image.subsurface(pygame.rect.FRect(3 * tile_width, 1 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(4 * tile_width, 1 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(5 * tile_width, 1 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(4 * tile_width, 1 * tile_height, tile_width, tile_height)),
        ],
        (MovementDirection.LEFT, MovementStatus.RUNNING): [
            image.subsurface(pygame.rect.FRect(3 * tile_width, 2 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(4 * tile_width, 2 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(5 * tile_width, 2 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(4 * tile_width, 2 * tile_height, tile_width, tile_height)),
        ],
        (MovementDirection.RIGHT, MovementStatus.RUNNING): [
            image.subsurface(pygame.rect.FRect(3 * tile_width, 3 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(4 * tile_width, 3 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(5 * tile_width, 3 * tile_height, tile_width, tile_height)),
            image.subsurface(pygame.rect.FRect(4 * tile_width, 3 * tile_height, tile_width, tile_height)),
        ],
    }


def get_min_area(items: Sequence[pygame.rect.FRect]) -> pygame.rect.FRect:
    min_x = min(rect.left for rect in items)
    max_x = max(rect.right for rect in items)
    min_y = min(rect.top for rect in items)
    max_y = max(rect.bottom for rect in items)
    return pygame.rect.FRect(0, 0, max_x - min_x, max_y - min_y)


def draw_grid(
    surface: pygame.surface.Surface,
    offset: pygame.math.Vector2 | None = None,
    tile_size: int = _TILE_SIZE,
) -> None:
    rect = surface.get_frect()
    if offset is None:
        offset = pygame.math.Vector2(0, 0)
    width, height = rect.size
    for x in range(int(offset.x % tile_size), int(width), tile_size):
        _ = pygame.draw.line(surface, color=BLACK, start_pos=(x, 0), end_pos=(x, height), width=1)
    for y in range(int(offset.y % tile_size), int(height), tile_size):
        _ = pygame.draw.line(surface, color=BLACK, start_pos=(0, y), end_pos=(width, y), width=1)


def debug_hitboxes(collision_group: CollisionGroup, camera: Camera) -> None:
    for rect in collision_group.items:
        _ = pygame.draw.rect(camera.surface, RED, rect.move(-camera.offset), width=1)


def debug(value: str, pos: Point = (10, 10)) -> None:
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
    _ = pygame.init()
    Game().run()
