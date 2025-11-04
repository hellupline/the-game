#!/usr/bin/env -S uv run python3

import json
from enum import StrEnum
from enum import auto
from operator import itemgetter
from pathlib import Path
from typing import Any
from typing import TypedDict
from typing import override
from uuid import UUID

ROOT_DIR = Path(__file__).resolve().parent

type Point = tuple[int, int]


class JSONEncoder(json.JSONEncoder):
    @override
    def default(self, obj: Any) -> Any:  # pyright: ignore[reportAny, reportExplicitAny, reportIncompatibleMethodOverride]
        if isinstance(obj, UUID):
            return str(obj)
        if isinstance(obj, set):
            return list(obj)  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        return json.JSONEncoder.default(self, obj)  # pyright: ignore[reportAny]


class HasId(TypedDict):
    id: UUID


class MapConfiguration(TypedDict):
    id: UUID
    walls: set[Point]
    warps: list[UUID]
    lancers: list[UUID]


class WarpConfiguration(TypedDict):
    id: UUID
    source_map_id: UUID
    source_map_position: Point
    target_map_id: UUID
    target_map_position: Point


class LancerConfiguration(TypedDict):
    id: UUID
    source_map_id: UUID
    source_map_position: Point
    route_type: RouteType
    route: list[Point]


class RouteType(StrEnum):
    SEQUENCE = auto()
    AREA = auto()


class TileType(StrEnum):
    EMPTY = "."
    WALL = "H"
    WARP = "O"
    LANCER = "l"
    PLAYER = "p"


def main() -> None:
    map1_id = UUID("7ff6603e-4a87-4114-806f-540194d63841")
    map1_warp1_id = UUID("942ba420-7ed5-48e1-b77f-c2ac89e01055")
    map1_lancer1_id = UUID("6b2c7696-0adf-40cc-ace6-e71ce4eb285f")
    map1_lancer2_id = UUID("840fcced-d657-4407-a183-378c15507da6")
    map2_id = UUID("34a81da6-3401-4e9d-8a48-db0136c1ada4")
    map2_warp1_id = UUID("2d6be514-ebf2-4326-8c4f-1d2555b7a0cb")
    map2_lancer1_id = UUID("f1c8e428-ab16-4cf6-9a7f-9ccb56b1b6d6")
    map1_configuration: MapConfiguration = {
        "id": map1_id,
        "walls": get_map_walls(ROOT_DIR / "map1_walls.txt"),
        "warps": [map1_warp1_id],
        "lancers": [map1_lancer1_id, map1_lancer2_id],
    }
    map1_warp1_configuration: WarpConfiguration = {
        "id": map1_warp1_id,
        "source_map_id": map1_id,
        "source_map_position": get_warp_position(ROOT_DIR / "map1_warp1_source.txt"),
        "target_map_id": map2_id,
        "target_map_position": get_warp_position(ROOT_DIR / "map1_warp1_target.txt"),
    }
    map1_lancer1_configuration: LancerConfiguration = {
        "id": map1_lancer1_id,
        "source_map_id": map1_id,
        "source_map_position": get_lancer_position(ROOT_DIR / "map1_lancer1_position.txt"),
        "route_type": RouteType.SEQUENCE,
        "route": get_lancer_route(ROOT_DIR / "map1_lancer1_route.txt"),
    }
    map1_lancer2_configuration: LancerConfiguration = {
        "id": map1_lancer2_id,
        "source_map_id": map1_id,
        "source_map_position": get_lancer_position(ROOT_DIR / "map1_lancer2_position.txt"),
        "route_type": RouteType.SEQUENCE,
        "route": get_lancer_route(ROOT_DIR / "map1_lancer2_route.txt"),
    }
    map2_configuration: MapConfiguration = {
        "id": map2_id,
        "walls": get_map_walls(ROOT_DIR / "map2_walls.txt"),
        "warps": [map2_warp1_id],
        "lancers": [map2_lancer1_id],
    }
    map2_warp1_configuration: WarpConfiguration = {
        "id": map2_warp1_id,
        "source_map_id": map2_id,
        "source_map_position": get_warp_position(ROOT_DIR / "map2_warp1_source.txt"),
        "target_map_id": map1_id,
        "target_map_position": get_warp_position(ROOT_DIR / "map2_warp1_target.txt"),
    }
    map2_lancer1_configuration: LancerConfiguration = {
        "id": map2_lancer1_id,
        "source_map_id": map2_id,
        "source_map_position": get_lancer_position(ROOT_DIR / "map2_lancer1_position.txt"),
        "route_type": RouteType.AREA,
        "route": get_lancer_route(ROOT_DIR / "map2_lancer1_route.txt"),
    }
    write_map(map1_configuration, "map1")
    write_warp(map1_warp1_configuration, "map1_warp1")
    write_lancer(map1_lancer1_configuration, "map1_lancer1")
    write_lancer(map1_lancer2_configuration, "map1_lancer2")
    write_map(map2_configuration, "map2")
    write_warp(map2_warp1_configuration, "map2_warp1")
    write_lancer(map2_lancer1_configuration, "map2_lancer1")


def write_map(configuration: MapConfiguration, name: str) -> None:
    write_data(configuration, name, ROOT_DIR / "maps")


def write_warp(configuration: WarpConfiguration, name: str) -> None:
    write_data(configuration, name, ROOT_DIR / "warps")


def write_lancer(configuration: LancerConfiguration, name: str) -> None:
    write_data(configuration, name, ROOT_DIR / "lancers")


def write_data(data: HasId, name: str, base_path: Path) -> None:
    filename = base_path / f"{data['id']}.json"
    link = base_path / f"{name}.link"
    with filename.open(mode="w") as f:
        json.dump(data, f, cls=JSONEncoder)
    if link.exists():
        link.unlink()
    link.symlink_to(filename.relative_to(base_path))


def get_map_walls(filename: Path) -> set[Point]:
    txt = filename.read_text().splitlines()
    return {
        (x, y)
        for y, row in enumerate(txt)
        for x, tile in enumerate(map(TileType, row))
        if tile == TileType.WALL
    }


def get_warp_position(filename: Path) -> Point:
    txt = filename.read_text().splitlines()
    for y, row in enumerate(txt):
        for x, tile in enumerate(map(TileType, row)):
            if tile == TileType.WARP:
                return (x, y)
    msg = "No warp found in the map."
    raise ValueError(msg)


def get_lancer_position(filename: Path) -> Point:
    txt = filename.read_text().splitlines()
    for y, row in enumerate(txt):
        for x, tile in enumerate(map(TileType, row)):
            if tile == TileType.LANCER:
                return (x, y)
    msg = "No lancer found in the map."
    raise ValueError(msg)


def get_lancer_route(filename: Path) -> list[Point]:
    txt = filename.read_text().splitlines()
    items = [(x, y, seq) for y, row in enumerate(txt) for x, seq in enumerate(row) if seq != "."]
    items = sorted(items, key=itemgetter(2))
    return [*map(itemgetter(0, 1), items)]


if __name__ == "__main__":
    main()
