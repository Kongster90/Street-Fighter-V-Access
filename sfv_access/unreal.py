"""Locating Unreal Engine's global name table inside the running game.

Everything in Unreal's object system is labelled by an FName, which is an index
into one global table. Resolving that table is the first milestone, because
without it an object is an anonymous blob and with it every object, class and
property has a readable name.

Nothing here relies on byte patterns lifted from another game. Street Fighter V
runs engine 4.7, which predates the published signatures, and its executable is
DRM wrapped so the file on disk cannot be searched anyway. Instead the table is
found by following references from a string that is certain to be in it, and
every candidate is checked by resolving names back out of it. A layout that can
produce "None" at index zero and sensible text either side of it is the right
layout; one that cannot is discarded.

Layout being searched for, on 64-bit builds of this engine era:

    FNameEntry
        0x00  int32   Index          index, with flag bits in the low end
        0x04          padding
        0x08  ptr     HashNext
        0x10  char[]  the name itself, narrow or wide

    TStaticIndirectArrayThreadSafeRead   (this is what GNames points at)
        0x00  ptr     Chunks[ChunkTableSize]
        ....  int32   NumElements
        ....  int32   NumChunks
"""

from __future__ import annotations

import struct
from dataclasses import dataclass, field

from .memory import ProcessMemory, Region

# Strings that exist in the name table of every Unreal game, used as the way in.
ANCHOR_NAMES = [b"ByteProperty\0", b"ObjectProperty\0", b"IntProperty\0", b"BoolProperty\0"]


@dataclass(frozen=True)
class NameLayout:
    """One hypothesis about how the name table is laid out."""

    name_offset: int = 0x10       # where the text sits inside an FNameEntry
    elements_per_chunk: int = 16384
    chunk_table_size: int = 128   # 2M max elements / 16384

    @property
    def count_offset(self) -> int:
        """NumElements sits directly after the chunk pointer table."""
        return self.chunk_table_size * 8

    def label(self) -> str:
        return (
            f"name+0x{self.name_offset:x}, {self.elements_per_chunk}/chunk, "
            f"{self.chunk_table_size} chunks"
        )


# Tried in order. The first is the standard shape for this engine era; the
# others cover a larger name budget or a different entry header.
LAYOUTS = [
    NameLayout(0x10, 16384, 128),
    NameLayout(0x10, 16384, 512),
    NameLayout(0x0C, 16384, 128),
    NameLayout(0x18, 16384, 128),
    NameLayout(0x10, 8192, 256),
]


@dataclass
class NameArray:
    address: int
    layout: NameLayout
    num_elements: int
    num_chunks: int
    samples: dict[int, str] = field(default_factory=dict)

    def describe(self) -> str:
        return (
            f"GNames at 0x{self.address:x} ({self.layout.label()}), "
            f"{self.num_elements:,} names in {self.num_chunks} chunks"
        )


def entry_text(pm: ProcessMemory, entry: int, layout: NameLayout) -> str | None:
    """The text of one FNameEntry, narrow or wide.

    The low bit of the header word marks a wide name in this engine era, so it
    is consulted rather than guessing from the bytes.
    """
    if entry <= 0x10000:
        return None
    header = pm.u32(entry)
    if header is None:
        return None
    is_wide = bool(header & 1)
    at = entry + layout.name_offset
    text = pm.wstring(at, 128) if is_wide else pm.cstring(at, 128)
    if not text:
        return None
    return text


def _plausible_name(text: str) -> bool:
    if not text or len(text) > 120:
        return False
    return all(32 <= ord(c) < 127 for c in text)


def read_name(pm: ProcessMemory, array: NameArray, index: int) -> str | None:
    layout = array.layout
    if index < 0 or index >= max(array.num_elements, 1):
        return None
    chunk_index, within = divmod(index, layout.elements_per_chunk)
    if chunk_index >= layout.chunk_table_size:
        return None
    chunk = pm.ptr(array.address + chunk_index * 8)
    if not chunk:
        return None
    entry = pm.ptr(chunk + within * 8)
    if not entry:
        return None
    return entry_text(pm, entry, layout)


def _score(pm: ProcessMemory, address: int, layout: NameLayout) -> NameArray | None:
    """Accept an address as the name table only if names actually come out."""
    count = pm.i32(address + layout.count_offset)
    chunks = pm.i32(address + layout.count_offset + 4)
    if count is None or chunks is None:
        return None
    if not (1000 < count < 4_000_000):
        return None
    expected = (count + layout.elements_per_chunk - 1) // layout.elements_per_chunk
    if not (0 < chunks <= layout.chunk_table_size) or abs(chunks - expected) > 1:
        return None

    array = NameArray(address, layout, count, chunks)
    first = read_name(pm, array, 0)
    if first != "None":
        return None

    # A handful of live indices should also come back as readable text.
    good, samples = 0, {}
    for idx in (1, 2, 3, 100, 1000, count // 2, count - 2):
        if not (0 <= idx < count):
            continue
        text = read_name(pm, array, idx)
        if text is not None and _plausible_name(text):
            good += 1
            if len(samples) < 6:
                samples[idx] = text
    if good < 4:
        return None
    array.samples = samples
    return array


@dataclass(frozen=True)
class ObjectLayout:
    """One hypothesis about UObjectBase's field offsets on 64-bit builds."""

    internal_index: int = 0x0C
    class_private: int = 0x10
    name_private: int = 0x18
    outer_private: int = 0x20
    elements_per_chunk: int = 16384
    chunk_table_size: int = 512

    @property
    def count_offset(self) -> int:
        return self.chunk_table_size * 8

    def label(self) -> str:
        return (
            f"index+0x{self.internal_index:x} class+0x{self.class_private:x} "
            f"name+0x{self.name_private:x} outer+0x{self.outer_private:x}, "
            f"{self.chunk_table_size} chunks"
        )


OBJECT_LAYOUTS = [
    ObjectLayout(0x0C, 0x10, 0x18, 0x20, 16384, 512),
    ObjectLayout(0x0C, 0x10, 0x18, 0x20, 16384, 128),
    ObjectLayout(0x08, 0x10, 0x18, 0x20, 16384, 512),
    ObjectLayout(0x14, 0x18, 0x20, 0x28, 16384, 512),
    ObjectLayout(0x0C, 0x18, 0x20, 0x28, 16384, 512),
]


@dataclass
class ObjectArray:
    """The engine's global object list.

    This build keeps it as a flat TArray of object pointers rather than the
    chunked array later versions use, so `address` is the array head: a data
    pointer, then the element count, then the allocated capacity. The chunked
    form is still supported because it is what the engine moved to.
    """

    address: int
    layout: ObjectLayout
    num_elements: int
    num_chunks: int = 0
    flat: bool = True
    capacity: int = 0

    def describe(self) -> str:
        shape = (
            f"flat array, {self.num_elements:,} of {self.capacity:,} slots"
            if self.flat
            else f"{self.num_elements:,} objects in {self.num_chunks} chunks"
        )
        return f"GObjects at 0x{self.address:x} ({self.layout.label()}), {shape}"


def object_at(pm: ProcessMemory, array: ObjectArray, index: int) -> int | None:
    if index < 0 or index >= array.num_elements:
        return None
    if array.flat:
        data = pm.ptr(array.address)
        if not data:
            return None
        return pm.ptr(data + index * 8) or None

    layout = array.layout
    chunk_index, within = divmod(index, layout.elements_per_chunk)
    if chunk_index >= layout.chunk_table_size:
        return None
    chunk = pm.ptr(array.address + chunk_index * 8)
    if not chunk:
        return None
    return pm.ptr(chunk + within * 8) or None


def object_name(
    pm: ProcessMemory, names: NameArray, obj: int, layout: ObjectLayout
) -> str | None:
    if not obj:
        return None
    index = pm.i32(obj + layout.name_private)
    if index is None or index < 0:
        return None
    base = read_name(pm, names, index)
    if base is None:
        return None
    # FName carries an occurrence number; anything above zero is printed as a
    # suffix by the engine, so mirror that.
    number = pm.i32(obj + layout.name_private + 4) or 0
    return f"{base}_{number - 1}" if number > 0 else base


def object_class_name(
    pm: ProcessMemory, names: NameArray, obj: int, layout: ObjectLayout
) -> str | None:
    cls = pm.ptr(obj + layout.class_private)
    if not cls:
        return None
    return object_name(pm, names, cls, layout)


def full_object_path(
    pm: ProcessMemory, names: NameArray, obj: int, layout: ObjectLayout, depth: int = 8
) -> str:
    """Name chain from the outermost package down to this object."""
    parts = []
    cur = obj
    seen = set()
    while cur and cur not in seen and len(parts) < depth:
        seen.add(cur)
        nm = object_name(pm, names, cur, layout)
        if nm is None:
            break
        parts.append(nm)
        cur = pm.ptr(cur + layout.outer_private) or 0
    return ".".join(reversed(parts))


def find_class_class(
    pm: ProcessMemory,
    names: NameArray,
    regions: list[Region],
    verbose: bool = True,
) -> tuple[int, ObjectLayout] | None:
    """Find the UClass object named "Class", the one object that points at itself.

    In Unreal every object records the class it belongs to, and the class of a
    class is UClass. So the object named "Class" is its own class, and that
    self-reference is a signature nothing else in memory shares. Matching it
    pins down where the name and class fields sit at the same time, which is
    exactly the pair of offsets the rest of the work needs.
    """
    name_index = None
    for i in range(min(names.num_elements, 4000)):
        if read_name(pm, names, i) == "Class":
            name_index = i
            break
    if name_index is None:
        return None
    if verbose:
        print(f"  name index of 'Class' is {name_index}")

    pattern = struct.pack("<ii", name_index, 0)
    hits = pm.find_bytes(pattern, regions, limit=20000, align=4)
    if verbose:
        print(f"  {len(hits)} places hold that FName")

    for layout in OBJECT_LAYOUTS:
        for hit in hits:
            obj = hit - layout.name_private
            if obj <= 0:
                continue
            if pm.ptr(obj + layout.class_private) != obj:
                continue  # not self-referential, so not UClass
            if object_name(pm, names, obj, layout) != "Class":
                continue
            if verbose:
                print(f"  UClass 'Class' at 0x{obj:x} with {layout.label()}")
            return obj, layout
    return None


def find_object_array(
    pm: ProcessMemory,
    names: NameArray,
    regions: list[Region],
    static_regions: list[Region],
    verbose: bool = True,
) -> ObjectArray | None:
    """Find the global object array by walking back from a known object.

    Sweeping the data section for a plausible chunk table does not work here:
    small integer pairs that happen to look like a count and a chunk count are
    everywhere, and none of them are the real thing. Following references is
    reliable instead, the same route that found the name table. Start from the
    UClass named "Class", use the index the object stores about itself to work
    out where in its chunk it must sit, and from the chunk find the table.
    """
    found = find_class_class(pm, names, regions, verbose=verbose)
    if found is None:
        if verbose:
            print("  could not find the UClass named 'Class'")
        return None
    anchor, layout = found

    internal = pm.i32(anchor + layout.internal_index)
    if internal is None or not (0 <= internal < 8_000_000):
        if verbose:
            print(f"  implausible internal index {internal}")
        return None

    slots = pm.find_pointers_to(anchor, regions, limit=6000)
    if verbose:
        print(f"  internal index {internal}, {len(slots)} pointers to it")

    # Most of those pointers are the class field of some other object. The real
    # one is a slot in the object list, so the test is what its neighbours look
    # like: entry i holds an object whose own recorded index is i. That is
    # checked with local reads, which keeps this to a handful of memory scans
    # instead of one per candidate.
    bases = []
    for slot in slots:
        start = slot - internal * 8
        if start > 0 and _chunk_looks_right(pm, start, 0, layout):
            bases.append(start)
    if verbose:
        print(f"  {len(bases)} of those sit in something shaped like the object list")
    if not bases:
        return None

    for data in bases:
        holders = pm.find_pointers_to(data, static_regions, limit=8)
        holders += [h for h in pm.find_pointers_to(data, regions, limit=16) if h not in holders]
        if verbose:
            print(f"  list data 0x{data:x}: referenced from {len(holders)} places")
        for holder in holders:
            # A TArray head is the data pointer, then the count, then capacity.
            count = pm.i32(holder + 8)
            capacity = pm.i32(holder + 12)
            if count is None or capacity is None:
                continue
            if not (1000 < count < 8_000_000) or not (count <= capacity <= count * 4 + 1024):
                continue
            candidate = ObjectArray(
                holder, layout, count, num_chunks=0, flat=True, capacity=capacity
            )
            if _object_array_ok(pm, names, candidate):
                if verbose:
                    print(f"  {candidate.describe()}")
                return candidate

        # Fall back to the chunked shape used by later engine versions.
        for holder in holders:
            for table_size in (512, 256, 128):
                shaped = ObjectLayout(
                    layout.internal_index,
                    layout.class_private,
                    layout.name_private,
                    layout.outer_private,
                    layout.elements_per_chunk,
                    table_size,
                )
                count = pm.i32(holder + shaped.count_offset)
                chunk_count = pm.i32(holder + shaped.count_offset + 4)
                if count is None or not (1000 < count < 8_000_000):
                    continue
                expected = (count + shaped.elements_per_chunk - 1) // shaped.elements_per_chunk
                if chunk_count is None or abs(chunk_count - expected) > 1:
                    continue
                candidate = ObjectArray(holder, shaped, count, chunk_count, flat=False)
                if _object_array_ok(pm, names, candidate):
                    if verbose:
                        print(f"  {candidate.describe()}")
                    return candidate
    return None


def _chunk_looks_right(
    pm: ProcessMemory, chunk: int, chunk_index: int, layout: ObjectLayout, probe: int = 48
) -> bool:
    """Does this address behave like a chunk of the object array?

    Entry i of chunk c holds an object that records its own index as
    c * ElementsPerChunk + i, so reading a run of entries and comparing is a
    decisive test that costs nothing but local reads.
    """
    raw = pm.read(chunk, probe * 8)
    if not raw:
        return False
    base_index = chunk_index * layout.elements_per_chunk
    agree = seen = 0
    for i in range(probe):
        obj = struct.unpack_from("<Q", raw, i * 8)[0]
        if not obj or obj < 0x10000:
            continue
        seen += 1
        if pm.i32(obj + layout.internal_index) == base_index + i:
            agree += 1
    return seen >= 12 and agree >= seen * 0.9


def _object_array_ok(pm: ProcessMemory, names: NameArray, array: ObjectArray) -> bool:
    """Accept only if objects come back with resolvable names and classes."""
    layout = array.layout
    good = 0
    checked = 0
    step = max(1, array.num_elements // 40)
    for index in range(0, min(array.num_elements, 40 * step), step):
        obj = object_at(pm, array, index)
        if not obj:
            continue
        checked += 1
        internal = pm.i32(obj + layout.internal_index)
        name = object_name(pm, names, obj, layout)
        cls = object_class_name(pm, names, obj, layout)
        if internal == index and name and cls and _plausible_name(name) and _plausible_name(cls):
            good += 1
    return checked >= 10 and good >= checked * 0.8


# Module offsets of the static pointer to the name table, found by the search
# below on this build. Checking them first turns a ninety second hunt into a
# single read; they are validated like any other candidate, so a game update
# that moves them costs nothing but a fallback to the full search.
KNOWN_GNAMES_OFFSETS = (0x3A75490, 0x3AD24A0)

# The global object list, likewise found once and then read directly.
KNOWN_GOBJECTS_OFFSETS = (0x3978730,)

# Field offsets confirmed against this build by the self-reference test on the
# UClass named "Class".
SFV_OBJECT_LAYOUT = ObjectLayout(
    internal_index=0x0C,
    class_private=0x10,
    name_private=0x18,
    outer_private=0x20,
)


def object_array_from_hint(
    pm: ProcessMemory,
    names: NameArray,
    module_base: int,
    offsets=KNOWN_GOBJECTS_OFFSETS,
) -> ObjectArray | None:
    for off in offsets:
        head = module_base + off
        count = pm.i32(head + 8)
        capacity = pm.i32(head + 12)
        if count is None or capacity is None:
            continue
        if not (1000 < count < 8_000_000) or not (count <= capacity):
            continue
        candidate = ObjectArray(
            head, SFV_OBJECT_LAYOUT, count, num_chunks=0, flat=True, capacity=capacity
        )
        if _object_array_ok(pm, names, candidate):
            return candidate
    return None


def name_array_from_hint(
    pm: ProcessMemory, module_base: int, offsets=KNOWN_GNAMES_OFFSETS
) -> NameArray | None:
    for off in offsets:
        address = pm.ptr(module_base + off)
        if not address:
            continue
        for layout in LAYOUTS:
            found = _score(pm, address, layout)
            if found is not None:
                return found
    return None


PROPERTY_CLASSES = {
    "ByteProperty", "IntProperty", "BoolProperty", "FloatProperty",
    "ObjectProperty", "NameProperty", "DelegateProperty", "ClassProperty",
    "ArrayProperty", "StructProperty", "StrProperty", "TextProperty",
    "InterfaceProperty", "MulticastDelegateProperty", "WeakObjectProperty",
    "LazyObjectProperty", "AssetObjectProperty", "UInt64Property",
    "UInt32Property", "UInt16Property", "Int64Property", "Int16Property",
    "Int8Property", "AssetSubclassOfProperty", "DoubleProperty",
    "SubclassOfProperty", "EnumProperty",
}
FIELD_CLASSES = PROPERTY_CLASSES | {"Function", "ScriptStruct", "Enum", "Const"}


@dataclass(frozen=True)
class StructLayout:
    """Where a class keeps its field list and where a property keeps its offset."""

    next_field: int = 0x28
    super_struct: int = 0x30
    children: int = 0x38
    properties_size: int = 0x40
    prop_array_dim: int = 0x30
    prop_element_size: int = 0x34
    prop_offset: int = 0x44

    def label(self) -> str:
        return (
            f"next+0x{self.next_field:x} super+0x{self.super_struct:x} "
            f"children+0x{self.children:x} size+0x{self.properties_size:x} "
            f"propoffset+0x{self.prop_offset:x}"
        )


@dataclass(frozen=True)
class Property:
    name: str
    type_name: str
    offset: int
    element_size: int
    array_dim: int
    address: int
    owner: str = ""  # the class that declares it, so inherited noise can be dropped


def walk_fields(
    pm: ProcessMemory, names: NameArray, owner: int, obj_layout: ObjectLayout,
    struct_layout: StructLayout, limit: int = 400
) -> list[int]:
    """The field objects a class declares, following its linked list."""
    out = []
    node = pm.ptr(owner + struct_layout.children) or 0
    seen = set()
    while node and node not in seen and len(out) < limit:
        seen.add(node)
        out.append(node)
        node = pm.ptr(node + struct_layout.next_field) or 0
    return out


def class_properties(
    pm: ProcessMemory, names: NameArray, owner: int, obj_layout: ObjectLayout,
    struct_layout: StructLayout, include_super: bool = True
) -> list[Property]:
    """Properties declared by a class, and by its parents when asked.

    Unreal stores a class's own fields only, so anything inherited has to be
    picked up by walking the chain of parent classes.
    """
    props: list[Property] = []
    chain, cur, seen = [], owner, set()
    while cur and cur not in seen:
        seen.add(cur)
        chain.append(cur)
        if not include_super:
            break
        cur = pm.ptr(cur + struct_layout.super_struct) or 0

    for cls in reversed(chain):
        owner = object_name(pm, names, cls, obj_layout) or ""
        for field in walk_fields(pm, names, cls, obj_layout, struct_layout):
            type_name = object_class_name(pm, names, field, obj_layout)
            if type_name not in PROPERTY_CLASSES:
                continue
            name = object_name(pm, names, field, obj_layout)
            offset = pm.i32(field + struct_layout.prop_offset)
            size = pm.i32(field + struct_layout.prop_element_size)
            dim = pm.i32(field + struct_layout.prop_array_dim)
            if name is None or offset is None or offset < 0 or offset > 0x20000:
                continue
            props.append(
                Property(name, type_name, offset, size or 0, dim or 1, field, owner)
            )
    props.sort(key=lambda p: p.offset)
    return props


def read_string(pm: ProcessMemory, address: int) -> str | None:
    """An FString, which is a length-counted array of wide characters."""
    data = pm.ptr(address)
    count = pm.i32(address + 8)
    if not data or count is None or not (0 < count < 4096):
        return None
    return pm.wstring(data, count)


def read_property(
    pm: ProcessMemory,
    names: NameArray,
    obj: int,
    prop: Property,
    obj_layout: ObjectLayout,
):
    """A property's value, decoded as far as its type allows."""
    at = obj + prop.offset
    kind = prop.type_name

    if kind == "BoolProperty":
        return bool(pm.u8(at))
    if kind in ("IntProperty", "Int32Property"):
        return pm.i32(at)
    if kind in ("ByteProperty", "Int8Property"):
        return pm.u8(at)
    if kind in ("UInt32Property", "Int64Property", "UInt64Property"):
        return pm.u64(at) if "64" in kind else pm.u32(at)
    if kind == "FloatProperty":
        return pm.f32(at)
    if kind == "StrProperty":
        return read_string(pm, at)
    if kind == "NameProperty":
        idx = pm.i32(at)
        return read_name(pm, names, idx) if idx is not None and idx >= 0 else None
    if kind in ("ObjectProperty", "ClassProperty", "WeakObjectProperty"):
        target = pm.ptr(at)
        if not target:
            return None
        return (
            f"{object_class_name(pm, names, target, obj_layout)} "
            f"{object_name(pm, names, target, obj_layout)}"
        )
    if kind == "ArrayProperty":
        data = pm.ptr(at)
        count = pm.i32(at + 8)
        if not data or count is None or not (0 <= count < 100000):
            return None
        return f"array of {count}"
    return None


def array_of_objects(
    pm: ProcessMemory, names: NameArray, address: int, obj_layout: ObjectLayout, cap: int = 64
) -> list[str]:
    """Contents of a TArray whose elements are object pointers."""
    data = pm.ptr(address)
    count = pm.i32(address + 8)
    if not data or not count or count < 0:
        return []
    out = []
    for i in range(min(count, cap)):
        target = pm.ptr(data + i * 8)
        if not target:
            continue
        out.append(
            f"{object_class_name(pm, names, target, obj_layout)} "
            f"{object_name(pm, names, target, obj_layout)}"
        )
    return out


def find_struct_layout(
    pm: ProcessMemory, names: NameArray, objects: ObjectArray, verbose: bool = True
) -> StructLayout | None:
    """Work out the class layout by insisting the field lists come out clean.

    A wrong guess produces chains of objects that are not properties at all, so
    the test is simply whether walking the list yields fields the engine
    recognises, and then whether their offsets fall inside the class they
    belong to.
    """
    layout = objects.layout
    classes = []
    for i in range(min(objects.num_elements, 60000)):
        obj = object_at(pm, objects, i)
        if obj and object_class_name(pm, names, obj, layout) == "Class":
            classes.append(obj)
        if len(classes) >= 300:
            break
    if verbose:
        print(f"  sampling {len(classes)} classes")

    best = None
    for next_off in (0x28, 0x30, 0x20):
        for children_off in (0x38, 0x30, 0x40, 0x48):
            if children_off == next_off:
                continue
            probe = StructLayout(next_field=next_off, children=children_off)
            total = good = 0
            for cls in classes[:120]:
                fields = walk_fields(pm, names, cls, layout, probe, limit=60)
                for f in fields:
                    total += 1
                    if object_class_name(pm, names, f, layout) in FIELD_CLASSES:
                        good += 1
            if total >= 200 and good >= total * 0.9:
                score = good
                if best is None or score > best[0]:
                    best = (score, next_off, children_off)
                    if verbose:
                        print(
                            f"  next+0x{next_off:x} children+0x{children_off:x}: "
                            f"{good}/{total} fields resolve"
                        )
    if best is None:
        return None
    _score_value, next_off, children_off = best

    # Now the property offset field, chosen by how well the values behave:
    # inside the class, distinct, and matching the declared struct size.
    partial = StructLayout(next_field=next_off, children=children_off)
    samples = []
    for cls in classes[:150]:
        fields = [
            f
            for f in walk_fields(pm, names, cls, layout, partial, limit=60)
            if object_class_name(pm, names, f, layout) in PROPERTY_CLASSES
        ]
        if len(fields) >= 4:
            samples.append((cls, fields))
        if len(samples) >= 60:
            break

    best_off, best_score = None, -1.0
    for cand in range(0x28, 0x80, 4):
        ok = seen = 0
        for _cls, fields in samples:
            values = [pm.i32(f + cand) for f in fields]
            if any(v is None for v in values):
                continue
            seen += len(values)
            for v in values:
                if 0 <= v <= 0x10000:
                    ok += 1
            # Declaration order usually means non-decreasing offsets.
            if values == sorted(values) and len(set(values)) == len(values):
                ok += len(values) // 2
        score = ok / seen if seen else 0
        if seen >= 100 and score > best_score:
            best_off, best_score = cand, score
    if best_off is None:
        return None
    if verbose:
        print(f"  property offset field at +0x{best_off:x} (score {best_score:.2f})")

    # ArrayDim and ElementSize sit at the front of UProperty, right after the
    # UField header, whatever the padding before Offset_Internal turns out to be.
    return StructLayout(
        next_field=next_off,
        children=children_off,
        prop_offset=best_off,
        prop_array_dim=0x30,
        prop_element_size=0x34,
    )


def _entry_indices(pm: ProcessMemory, entry: int) -> list[int]:
    """Candidate name indices from an entry header, which packs flag bits."""
    header = pm.u32(entry)
    if header is None:
        return []
    out = []
    for value in (header >> 1, header, header >> 2):
        if 0 < value < 4_000_000 and value not in out:
            out.append(value)
    return out


def find_name_array(
    pm: ProcessMemory,
    regions: list[Region] | None = None,
    static_regions: list[Region] | None = None,
    verbose: bool = True,
) -> NameArray | None:
    """Find GNames by following references from a name that must be in it.

    The chain runs: the text of a known name, the FNameEntry wrapping it, the
    chunk slot pointing at that entry, the chunk itself, and the table whose
    pointer list holds the chunk.

    Two things keep this to a handful of passes instead of a search. The entry
    header carries the name's own index, which gives the slot's position within
    its chunk directly, so the chunk start is arithmetic rather than a hunt.
    And the table is a static global, so the game's own data section is tried
    before the rest of the address space.
    """
    regions = regions or pm.regions()
    search_first = static_regions or []
    if verbose:
        total = sum(r.size for r in regions) / 1e9
        print(f"searching {len(regions)} regions, {total:.2f} GB")

    for anchor in ANCHOR_NAMES:
        wanted = anchor[:-1].decode()
        text_hits = pm.find_bytes(anchor, regions, limit=24)
        if verbose:
            print(f"  anchor {wanted!r}: {len(text_hits)} occurrences")
        if not text_hits:
            continue

        for layout in LAYOUTS:
            entries = [
                h - layout.name_offset
                for h in text_hits
                if h > layout.name_offset
                and entry_text(pm, h - layout.name_offset, layout) == wanted
            ]
            if not entries:
                continue
            if verbose:
                print(f"    {layout.label()}: {len(entries)} entry candidates")

            for entry in entries[:6]:
                slots = pm.find_pointers_to(entry, regions, limit=16)
                if not slots:
                    continue
                indices = _entry_indices(pm, entry)
                for slot in slots:
                    for index in indices:
                        within = index % layout.elements_per_chunk
                        chunk_index = index // layout.elements_per_chunk
                        if chunk_index >= layout.chunk_table_size:
                            continue
                        chunk = slot - within * 8
                        holders = pm.find_pointers_to(chunk, search_first, limit=8)
                        holders += pm.find_pointers_to(chunk, regions, limit=8)
                        for holder in holders:
                            base = holder - chunk_index * 8
                            found = _score(pm, base, layout)
                            if found is not None:
                                if verbose:
                                    print(f"  {found.describe()}")
                                return found
    return None
