#!/usr/bin/env python3
"""
Graph Core Engine with customizable binary edge format.

This module provides a high‑performance, low‑level storage and algorithm
suite for directed graphs where edges are stored as fixed‑length binary
records. The schema of an edge is fully configurable (field names, types,
byte sizes). Optimized algorithms from graph theory (topological sort,
critical path, SCC, shortest paths) are implemented with minimal overhead.
"""

import struct
from collections import defaultdict, deque
from typing import Dict, List, Tuple, Optional, Set, Iterator, Any
import unittest
import random
import time


# ----------------------------------------------------------------------
#  Field and Schema Definition
# ----------------------------------------------------------------------

class Field:
    """Describes a single field within a binary edge record."""
    __slots__ = ('name', 'fmt', 'size', 'offset', 'dtype')
    _format_map = {
        'uint8': ('B', 1),
        'int8': ('b', 1),
        'uint16': ('H', 2),
        'int16': ('h', 2),
        'uint32': ('I', 4),
        'int32': ('i', 4),
        'uint64': ('Q', 8),
        'int64': ('q', 8),
    }

    def __init__(self, name: str, dtype: str):
        if dtype not in self._format_map:
            raise ValueError(f'Unsupported dtype {dtype}')
        self.name = name
        self.dtype = dtype
        self.fmt, self.size = self._format_map[dtype]
        self.offset = 0

    def __repr__(self) -> str:
        return f'Field(name={self.name!r}, dtype={self.dtype!r}, size={self.size})'


class EdgeSchema:
    """Defines the binary layout of an edge record."""

    def __init__(self, fields: List[Field]):
        self.fields = fields
        self.total_size = 0
        self.offsets = {}
        self.field_map = {f.name: f for f in fields}
        fmt_parts = []

        for f in fields:
            f.offset = self.total_size
            self.offsets[f.name] = f.offset
            fmt_parts.append(f.fmt)
            self.total_size += f.size

        self._struct = struct.Struct('<' + ''.join(fmt_parts))
        self._field_names = [f.name for f in fields]

    def pack(self, **kwargs) -> bytes:
        values = [kwargs[name] for name in self._field_names]
        return self._struct.pack(*values)

    def unpack(self, data: bytes) -> Dict[str, Any]:
        values = self._struct.unpack(data)
        return dict(zip(self._field_names, values))

    def pack_into(self, buffer: bytearray, offset: int, **kwargs) -> None:
        values = [kwargs[name] for name in self._field_names]
        self._struct.pack_into(buffer, offset, *values)

    def unpack_from(self, buffer: bytearray, offset: int) -> Dict[str, Any]:
        values = self._struct.unpack_from(buffer, offset)
        return dict(zip(self._field_names, values))

    @property
    def num_fields(self) -> int:
        return len(self.fields)

    def get_field_dtype(self, field_name: str) -> str:
        if field_name in self.field_map:
            return self.field_map[field_name].dtype
        return 'uint16'

    def get_max_value(self, field_name: str) -> int:
        dtype = self.get_field_dtype(field_name)
        if 'uint8' in dtype:
            return 255
        elif 'uint16' in dtype:
            return 65535
        elif 'uint32' in dtype:
            return 4294967295
        elif 'int8' in dtype:
            return 127
        elif 'int16' in dtype:
            return 32767
        elif 'int32' in dtype:
            return 2147483647
        return 65535

    def __repr__(self) -> str:
        return f'EdgeSchema(total_size={self.total_size}, fields={self.fields})'


# ----------------------------------------------------------------------
#  Graph Storage – compact binary edge container
# ----------------------------------------------------------------------

class GraphStorage:
    """Stores edges as a contiguous array of fixed‑length binary records."""

    __slots__ = ('schema', 'source_field', 'target_field', '_buffer', '_num_edges')

    def __init__(self, schema: EdgeSchema, source_field: str, target_field: str):
        self.schema = schema
        self.source_field = source_field
        self.target_field = target_field

        if source_field not in schema.offsets:
            raise KeyError(f'Source field {source_field!r} not in schema')
        if target_field not in schema.offsets:
            raise KeyError(f'Target field {target_field!r} not in schema')

        self._buffer = bytearray()
        self._num_edges = 0

    @property
    def num_edges(self) -> int:
        return self._num_edges

    @property
    def buffer_size(self) -> int:
        return len(self._buffer)

    def add_edge(self, **fields) -> int:
        for fname in self.schema._field_names:
            if fname not in fields:
                raise ValueError(f'Missing field {fname!r} in edge data')

        for field_name, value in fields.items():
            if field_name in self.schema.offsets:
                max_val = self.schema.get_max_value(field_name)
                if not isinstance(value, (int, float)):
                    raise ValueError(f'{field_name} must be a number, got {type(value)}')
                if value < 0 or value > max_val:
                    raise ValueError(
                        f'{field_name} {value} out of range for {self.schema.get_field_dtype(field_name)} (0-{max_val})')

        start = self._num_edges * self.schema.total_size
        self._buffer.extend(b'\x00' * self.schema.total_size)
        self.schema.pack_into(self._buffer, start, **fields)
        self._num_edges += 1
        return self._num_edges - 1

    def get_edge(self, idx: int) -> Dict[str, Any]:
        if idx < 0 or idx >= self._num_edges:
            raise IndexError('Edge index out of range')
        offset = idx * self.schema.total_size
        return self.schema.unpack_from(self._buffer, offset)

    def get_vertices(self) -> Set[int]:
        vertices = set()
        src_ofs = self.schema.offsets[self.source_field]
        tgt_ofs = self.schema.offsets[self.target_field]

        src_field = self.schema.field_map[self.source_field]
        tgt_field = self.schema.field_map[self.target_field]

        src_unpack = struct.Struct('<' + src_field.fmt).unpack_from
        tgt_unpack = struct.Struct('<' + tgt_field.fmt).unpack_from
        sz = self.schema.total_size

        for i in range(self._num_edges):
            offset = i * sz
            vertices.add(src_unpack(self._buffer, offset + src_ofs)[0])
            vertices.add(tgt_unpack(self._buffer, offset + tgt_ofs)[0])
        return vertices

    def adjacency_lists_fast(self) -> Tuple[Dict[int, List[Tuple[int, int, int]]],
    Dict[int, List[Tuple[int, int, int]]]]:
        out = defaultdict(list)
        inn = defaultdict(list)
        sz = self.schema.total_size

        src_ofs = self.schema.offsets[self.source_field]
        tgt_ofs = self.schema.offsets[self.target_field]

        src_field = self.schema.field_map[self.source_field]
        tgt_field = self.schema.field_map[self.target_field]

        src_unpack = struct.Struct('<' + src_field.fmt).unpack_from
        tgt_unpack = struct.Struct('<' + tgt_field.fmt).unpack_from

        dur_unpack = None
        dur_ofs = self.schema.offsets.get('duration')
        if dur_ofs is not None:
            dur_field = self.schema.field_map.get('duration')
            if dur_field:
                dur_unpack = struct.Struct('<' + dur_field.fmt).unpack_from

        for i in range(self._num_edges):
            offset = i * sz
            src = src_unpack(self._buffer, offset + src_ofs)[0]
            tgt = tgt_unpack(self._buffer, offset + tgt_ofs)[0]
            dur = dur_unpack(self._buffer, offset + dur_ofs)[0] if dur_unpack else 0
            out[src].append((tgt, i, dur))
            inn[tgt].append((src, i, dur))

        return out, inn


# ----------------------------------------------------------------------
#  Advanced Graph Algorithms - FIXED VERSION
# ----------------------------------------------------------------------

class GraphAlgorithms:
    """Collection of ultra‑fast graph algorithms."""

    @staticmethod
    def topological_sort(storage: GraphStorage) -> List[int]:
        out_edges, in_edges = storage.adjacency_lists_fast()
        vertices = storage.get_vertices()

        indegree = {v: len(in_edges[v]) for v in vertices}
        q = deque([v for v in indegree if indegree[v] == 0])
        order = []

        while q:
            v = q.popleft()
            order.append(v)
            for tgt, _, _ in out_edges.get(v, []):
                indegree[tgt] -= 1
                if indegree[tgt] == 0:
                    q.append(tgt)

        if len(order) != len(vertices):
            raise ValueError('Graph contains a cycle')
        return order

    @staticmethod
    def is_dag(storage: GraphStorage) -> bool:
        try:
            GraphAlgorithms.topological_sort(storage)
            return True
        except ValueError:
            return False

    @staticmethod
    def strongly_connected_components(storage: GraphStorage) -> List[List[int]]:
        out_edges, _ = storage.adjacency_lists_fast()
        vertices = storage.get_vertices()

        index = 0
        stack = []
        indices = {}
        lowlinks = {}
        on_stack = set()
        sccs = []

        def strongconnect(v):
            nonlocal index
            indices[v] = index
            lowlinks[v] = index
            index += 1
            stack.append(v)
            on_stack.add(v)

            for w, _, _ in out_edges.get(v, []):
                if w not in indices:
                    strongconnect(w)
                    lowlinks[v] = min(lowlinks[v], lowlinks[w])
                elif w in on_stack:
                    lowlinks[v] = min(lowlinks[v], indices[w])

            if lowlinks[v] == indices[v]:
                scc = []
                while True:
                    w = stack.pop()
                    on_stack.remove(w)
                    scc.append(w)
                    if w == v:
                        break
                sccs.append(scc)

        for v in vertices:
            if v not in indices:
                strongconnect(v)

        return sccs

    @staticmethod
    def has_cycle_ultra_fast(storage: GraphStorage) -> Tuple[bool, int]:
        """
        FIXED: Proper cycle detection using DFS with colors.
        Returns (has_cycle, cycle_count)
        """
        out_edges, _ = storage.adjacency_lists_fast()
        vertices = storage.get_vertices()

        # 0 = unvisited, 1 = visiting, 2 = visited
        state = {v: 0 for v in vertices}
        cycle_count = 0
        has_cycle = False

        def dfs(v: int):
            nonlocal cycle_count, has_cycle
            state[v] = 1

            for w, _, _ in out_edges.get(v, []):
                if w not in state:
                    continue
                if state[w] == 1:
                    cycle_count += 1
                    has_cycle = True
                    if cycle_count > 100:  # Limit for performance
                        return
                elif state[w] == 0:
                    dfs(w)
                    if has_cycle and cycle_count > 100:
                        return

            state[v] = 2

        try:
            for v in vertices:
                if state[v] == 0:
                    dfs(v)
                    if has_cycle and cycle_count > 100:
                        break
        except RecursionError:
            return GraphAlgorithms._has_cycle_iterative(out_edges, vertices), cycle_count

        return has_cycle, cycle_count

    @staticmethod
    def _has_cycle_iterative(out_edges: Dict, vertices: Set[int]) -> bool:
        """Iterative DFS for cycle detection."""
        state = {v: 0 for v in vertices}

        for start in vertices:
            if state[start] != 0:
                continue

            stack = [(start, iter(out_edges.get(start, [])))]
            state[start] = 1

            while stack:
                v, it = stack[-1]
                try:
                    w = next(it)
                    if w not in state:
                        continue
                    if state[w] == 1:
                        return True
                    if state[w] == 0:
                        state[w] = 1
                        stack.append((w, iter(out_edges.get(w, []))))
                except StopIteration:
                    state[v] = 2
                    stack.pop()

        return False

    @staticmethod
    def find_cycles_ultra_fast(storage: GraphStorage, max_cycles: int = 10,
                               force_vertices: List[int] = None) -> List[List[int]]:
        out_edges, _ = storage.adjacency_lists_fast()
        vertices = list(storage.get_vertices())
        cycles = []
        seen_cycles = set()

        max_depth = 20
        max_vertices = min(100, len(vertices))

        if force_vertices:
            vertex_set = storage.get_vertices()
            start_vertices = [v for v in force_vertices if v in vertex_set]
        else:
            start_vertices = random.sample(vertices, min(max_vertices, len(vertices)))

        for start in start_vertices:
            if len(cycles) >= max_cycles:
                break

            stack = [(start, [start])]
            visited_at_depth = {start: 0}

            while stack and len(cycles) < max_cycles:
                v, path = stack.pop()

                if len(path) > max_depth:
                    continue

                for w, _, _ in out_edges.get(v, []):
                    if w == start and len(path) > 1:
                        cycle_key = tuple(sorted(set(path)))
                        if cycle_key not in seen_cycles:
                            seen_cycles.add(cycle_key)
                            cycles.append(path.copy())
                        break

                    if w not in path and w not in visited_at_depth:
                        visited_at_depth[w] = len(path)
                        stack.append((w, path + [w]))

        return cycles[:max_cycles]

    @staticmethod
    def critical_path(storage: GraphStorage, weight_field: str) -> Tuple[int, List[int]]:
        if not GraphAlgorithms.is_dag(storage):
            raise ValueError('Critical path requires a DAG.')

        out_edges, _ = storage.adjacency_lists_fast()
        vertices = storage.get_vertices()
        topo_order = GraphAlgorithms.topological_sort(storage)

        dist = {v: 0 for v in vertices}
        predecessor = {v: None for v in vertices}

        for v in topo_order:
            for tgt, _, dur in out_edges.get(v, []):
                if dist[v] + dur > dist[tgt]:
                    dist[tgt] = dist[v] + dur
                    predecessor[tgt] = v

        end_vertex = max(dist.items(), key=lambda x: x[1])[0]
        max_dist = dist[end_vertex]

        path = []
        cur = end_vertex
        while cur is not None:
            path.append(cur)
            cur = predecessor[cur]
        path.reverse()

        return max_dist, path

    @staticmethod
    def shortest_path(storage: GraphStorage,
                      source: int,
                      target: int,
                      weight_field: Optional[str] = None) -> Tuple[Optional[float], List[int]]:
        out_edges, _ = storage.adjacency_lists_fast()
        vertices = storage.get_vertices()

        if weight_field is None:
            visited = {source}
            q = deque([(source, 0, [source])])
            while q:
                v, d, path = q.popleft()
                if v == target:
                    return d, path
                for tgt, _, _ in out_edges.get(v, []):
                    if tgt not in visited:
                        visited.add(tgt)
                        q.append((tgt, d + 1, path + [tgt]))
            return None, []

        import heapq
        dist = {v: float('inf') for v in vertices}
        prev = {v: None for v in vertices}
        dist[source] = 0
        pq = [(0.0, source)]

        while pq:
            d, v = heapq.heappop(pq)
            if d > dist[v]:
                continue
            if v == target:
                break
            for tgt, _, weight in out_edges.get(v, []):
                nd = d + weight
                if nd < dist[tgt]:
                    dist[tgt] = nd
                    prev[tgt] = v
                    heapq.heappush(pq, (nd, tgt))

        if dist[target] == float('inf'):
            return None, []

        path = []
        cur = target
        while cur is not None:
            path.append(cur)
            cur = prev[cur]
        path.reverse()
        return dist[target], path


# ----------------------------------------------------------------------
#  Extended Schema and Graph Generator
# ----------------------------------------------------------------------

def make_extended_schema():
    return EdgeSchema([
        Field('source', 'uint16'),
        Field('target', 'uint16'),
        Field('type', 'uint8'),
        Field('priority', 'uint8'),
        Field('duration', 'uint16'),
        Field('flags', 'uint8'),
        Field('team', 'uint8'),
        Field('complexity', 'uint8'),
        Field('reserved', 'uint16'),
    ])


def generate_complex_task_graph_ultra_fast(storage, num_tasks=5000, num_edges=15000):
    print(f"Generating {num_edges} complex task dependencies across {num_tasks} tasks...")

    import random

    task_ids = []
    task_metadata = {}

    modules = list(range(1, 31))
    layers = list(range(1, 16))

    task_types = [1, 2, 3, 4]
    priorities = list(range(6))
    teams = list(range(1, 9))
    complexities = list(range(4))

    total_generated = 0
    target_tasks = int(num_tasks * 1.2)

    for module in modules:
        if total_generated >= target_tasks:
            break
        for layer in layers:
            if total_generated >= target_tasks:
                break
            num_tasks_in_layer = random.randint(2, 4)
            for subtask in range(1, num_tasks_in_layer + 1):
                task_id = module * 1000 + layer * 100 + subtask
                if task_id > 65535:
                    continue

                task_ids.append(task_id)
                task_metadata[task_id] = {
                    'module': module,
                    'layer': layer,
                    'subtask': subtask,
                    'type': random.choice(task_types),
                    'priority': random.choice(priorities),
                    'team': random.choice(teams),
                    'complexity': random.choice(complexities),
                    'base_duration': random.randint(1, 12)
                }
                total_generated += 1

    if len(task_ids) > num_tasks:
        task_ids = random.sample(task_ids, num_tasks)

    task_set = set(task_ids)
    task_metadata = {tid: task_metadata[tid] for tid in task_set if tid in task_metadata}
    task_ids = list(task_set)

    edge_count = 0
    max_attempts = num_edges * 2

    for attempt in range(max_attempts):
        if edge_count >= num_edges:
            break

        source = random.choice(task_ids)
        target = random.choice(task_ids)

        if source == target:
            continue

        if source not in task_metadata or target not in task_metadata:
            continue

        src_meta = task_metadata[source]
        tgt_meta = task_metadata[target]

        if src_meta['layer'] > tgt_meta['layer']:
            source, target = target, source
            src_meta, tgt_meta = tgt_meta, src_meta

        layer_diff = max(1, tgt_meta['layer'] - src_meta['layer'])
        duration = int(src_meta['base_duration'] * layer_diff * random.uniform(0.8, 1.5))
        duration = max(1, min(65535, duration))

        flags = 0
        if src_meta['module'] != tgt_meta['module']:
            flags |= 0x01
        if random.random() < 0.15:
            flags |= 0x02
        if random.random() < 0.1:
            flags |= 0x04

        try:
            storage.add_edge(
                source=source,
                target=target,
                type=tgt_meta['type'],
                priority=tgt_meta['priority'],
                duration=duration,
                flags=flags,
                team=tgt_meta['team'],
                complexity=tgt_meta['complexity'],
                reserved=0
            )
            edge_count += 1

            if edge_count % 1000 == 0:
                print(f"    Generated {edge_count} edges...", flush=True)

        except (struct.error, ValueError):
            continue

    print(f"\n✅ Generated {edge_count} complex task dependencies")
    return task_ids, task_metadata


# ----------------------------------------------------------------------
#  Unit Tests
# ----------------------------------------------------------------------

class TestGraphCore(unittest.TestCase):
    def setUp(self):
        self.schema = make_extended_schema()
        self.storage = GraphStorage(self.schema, 'source', 'target')

    def test_edge_crud(self):
        idx = self.storage.add_edge(source=1, target=2, type=1, priority=2,
                                    duration=5, flags=0, team=1, complexity=1, reserved=0)
        self.assertEqual(self.storage.num_edges, 1)
        edge = self.storage.get_edge(idx)
        self.assertEqual(edge['source'], 1)
        self.assertEqual(edge['target'], 2)

        with self.assertRaises(ValueError):
            self.storage.add_edge(source=70000, target=2, type=1, priority=2,
                                  duration=5, flags=0, team=1, complexity=1, reserved=0)

    def test_cycle_detection(self):
        # Clear storage and create a simple cycle
        self.storage = GraphStorage(self.schema, 'source', 'target')

        self.storage.add_edge(source=1, target=2, type=1, priority=2,
                              duration=5, flags=0, team=1, complexity=1, reserved=0)
        self.storage.add_edge(source=2, target=3, type=1, priority=2,
                              duration=5, flags=0, team=1, complexity=1, reserved=0)
        self.storage.add_edge(source=3, target=1, type=1, priority=2,
                              duration=5, flags=0, team=1, complexity=1, reserved=0)

        # Test has_cycle_ultra_fast - FIXED
        has_cycle, count = GraphAlgorithms.has_cycle_ultra_fast(self.storage)
        self.assertTrue(has_cycle, f"Expected cycle but got has_cycle={has_cycle}, count={count}")
        self.assertGreater(count, 0)

        # Test find_cycles_ultra_fast
        cycles = GraphAlgorithms.find_cycles_ultra_fast(self.storage, max_cycles=5, force_vertices=[1])
        self.assertGreaterEqual(len(cycles), 1)

        found = False
        for cycle in cycles:
            if set(cycle) == {1, 2, 3}:
                found = True
                break
        self.assertTrue(found, f"Cycle [1,2,3] not found in {cycles}")


# ----------------------------------------------------------------------
#  Ultra-Fast Demo
# ----------------------------------------------------------------------

def ultra_fast_demo():
    print("=== Graph Core Engine - ULTRA FAST Demo ===\n")

    schema = make_extended_schema()
    storage = GraphStorage(schema, 'source', 'target')

    print(f"Edge schema: {schema.total_size} bytes per edge")
    print(f"Fields: {[f.name for f in schema.fields]}\n")

    start_gen = time.time()
    task_ids, metadata = generate_complex_task_graph_ultra_fast(storage, num_tasks=500000, num_edges=1500000)
    gen_time = time.time() - start_gen

    print(f"\n📊 Graph Statistics:")
    print(f"  Total edges: {storage.num_edges}")
    print(f"  Storage size: {storage.buffer_size / 1024:.1f} KB")
    print(f"  Bytes per edge: {storage.buffer_size / max(1, storage.num_edges):.1f}")
    print(f"  Total vertices: {len(storage.get_vertices())}")
    print(f"  Generation time: {gen_time:.2f}s")

    print(f"\n🔍 Graph Analysis:")

    start = time.time()
    is_dag = GraphAlgorithms.is_dag(storage)
    dag_time = time.time() - start
    print(f"  Is DAG: {is_dag} ({dag_time * 1000:.1f} ms)")

    start = time.time()
    sccs = GraphAlgorithms.strongly_connected_components(storage)
    scc_time = time.time() - start
    print(f"  SCCs: {len(sccs)} ({scc_time * 1000:.1f} ms)")

    # FIXED: Now correctly reports cycles
    start = time.time()
    has_cycle, approx_cycles = GraphAlgorithms.has_cycle_ultra_fast(storage)
    cycle_time = time.time() - start
    print(f"  Has cycle: {has_cycle} ({approx_cycles} cycles detected) ({cycle_time * 1000:.1f} ms)")

    if has_cycle:
        start = time.time()
        cycles = GraphAlgorithms.find_cycles_ultra_fast(storage, max_cycles=10)
        sample_time = time.time() - start
        print(f"  Sample cycles: {len(cycles)} found ({sample_time * 1000:.1f} ms)")
        if cycles:
            cycle_str = ' → '.join(map(str, cycles[0][:5]))
            print(f"  First cycle: {cycle_str}... (len={len(cycles[0])})")

    print(f"\n⚡ Performance Test:")

    start = time.perf_counter()
    out_edges, in_edges = storage.adjacency_lists_fast()
    adj_time = time.perf_counter() - start
    print(f"  Fast adjacency: {adj_time * 1000:.3f} ms")

    vertices = list(storage.get_vertices())
    if len(vertices) >= 2:
        v1, v2 = random.sample(vertices, 2)
        start = time.perf_counter()
        dist, path = GraphAlgorithms.shortest_path(storage, v1, v2, weight_field='duration')
        path_time = time.perf_counter() - start
        if dist:
            print(f"  Shortest path ({v1} → {v2}): {dist:.0f}h, {len(path)} steps, {path_time * 1000:.3f} ms")

    print(f"\n💾 Memory Efficiency:")
    json_est = storage.num_edges * 200
    print(f"  JSON: {json_est / 1024:.1f} KB")
    print(f"  Binary: {storage.buffer_size / 1024:.1f} KB")
    print(f"  Ratio: {json_est / storage.buffer_size:.1f}x")

    total_time = time.time() - start_gen
    print(f"\n⏱️  Total demo time: {total_time:.2f}s")
    print(f"\n{'=' * 60}")
    print(f"✅ ULTRA FAST Demo complete!")


if __name__ == '__main__':
    unittest.main(argv=[''], exit=False, verbosity=1)
    print("\n" + "=" * 60 + "\n")
    ultra_fast_demo()