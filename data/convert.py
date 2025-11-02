#!/usr/bin/env -S uv run python3

import json
import pathlib
from enum import StrEnum
from operator import itemgetter
from typing import Any
from typing import Literal
from typing import TypedDict
from typing import override

type Point = tuple[int, int]
type MapName = Literal["map1", "map2"]
type RouteType = Literal["sequence", "area"]


class JSONEncoder(json.JSONEncoder):
    @override
    def default(self, obj: Any) -> Any:  # pyright: ignore[reportAny, reportExplicitAny, reportIncompatibleMethodOverride]
        if isinstance(obj, set):
            return list(obj)  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        return json.JSONEncoder.default(self, obj)  # pyright: ignore[reportAny]


class MapConfiguration(TypedDict):
    walls: set[Point]
    warps: list[WarpConfiguration]
    lancers: list[LancerConfiguration]
    player_position: Point


class WarpConfiguration(TypedDict):
    position: Point
    target: MapName


class LancerConfiguration(TypedDict):
    position: Point
    route_type: RouteType
    route: list[Point]


class TileType(StrEnum):
    EMPTY = "."
    WALL = "H"
    WARP = "O"
    LANCER = "l"
    PLAYER = "p"


def main() -> None:
    map_filename = pathlib.Path("./data/map1.txt")
    lancer_map_filenames = [
        pathlib.Path("./data/map1_lancer1.txt"),
        pathlib.Path("./data/map1_lancer2.txt"),
    ]
    with pathlib.Path("./data/map1.json").open("w") as f:
        json.dump(get_map_configuration(map_filename, lancer_map_filenames), f, cls=JSONEncoder)

    map_filename = pathlib.Path("./data/map2.txt")
    lancer_map_filenames = [
        pathlib.Path("./data/map2_lancer1.txt"),
    ]
    with pathlib.Path("./data/map2.json").open("w") as f:
        json.dump(get_map_configuration(map_filename, lancer_map_filenames), f, cls=JSONEncoder)


def get_map_configuration(
    map_filename: pathlib.Path,
    lancer_map_filenames: list[pathlib.Path],
) -> MapConfiguration:
    txt = map_filename.read_text().splitlines()
    walls: set[Point] = set()
    warps: list[WarpConfiguration] = []
    lancers: list[LancerConfiguration] = []
    player_position: Point = (1, 1)
    warp: WarpConfiguration
    lancer: LancerConfiguration
    for y, row in enumerate(txt):
        for x, tile in enumerate(map(TileType, row)):
            if tile == TileType.WALL:
                walls.add((x, y))
            elif tile == TileType.WARP:
                warp = {"position": (x, y), "target": "map2"}
                warps.append(warp)
            elif tile == TileType.LANCER:
                lancer = {
                    "position": (x, y),
                    "route_type": "sequence",
                    "route": [],
                }
                lancers.append(lancer)
            elif tile == TileType.PLAYER:
                player_position = (x, y)
    return {
        "walls": walls,
        "warps": warps,
        "lancers": [
            {**lancer, "route": route, "route_type": route_type}
            for lancer, (route, route_type) in zip(
                lancers,
                map(get_lancer_route, lancer_map_filenames),
                strict=False,
            )
        ],
        "player_position": player_position,
    }


def get_lancer_route(lancer_map_filename: pathlib.Path) -> tuple[list[Point], RouteType]:
    txt = lancer_map_filename.read_text().splitlines()
    items = [(x, y, seq) for y, row in enumerate(txt) for x, seq in enumerate(row) if seq != "."]
    items = sorted(items, key=itemgetter(2))
    route = [*map(itemgetter(0, 1), items)]
    route_type = "sequence"
    if len(set(map(itemgetter(2), items))) == 1:
        route_type = "area"
    return route, route_type


if __name__ == "__main__":
    main()
