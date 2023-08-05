#!/usr/bin/env python3
#
# SPDX-FileCopyrightText: 2019 Francesco Tamagni <mrmacete@protonmail.ch>
# SPDX-License-Identifier: LGPL-3.0-only
#
# -*- coding: utf-8 -*-

"""
Example usage to regenerate traps.json:
    - open the dyld cache in rizin like this:
RZ_DYLDCACHE_FILTER=libsystem_kernel rizin -e bin.usextr=false ~/Library/Developer/Xcode/iOS\ DeviceSupport/12.1.2\ \(16C101\)\ arm64e/Symbols/System/Library/Caches/com.apple.dyld/dyld_shared_cache_arm64e

    - run the script with this command:
        #!pipe python3 /path/to/this/script.py > traps.json

"""

import json
import re

import rzpipe

r = rzpipe.open()


def walk_back_until(addr, pattern, min_addr):
    cursor = addr
    while cursor >= min_addr:
        op = r.cmdj(f"aoj@{str(cursor)}")[0]["opcode"]
        if re.search(pattern, op) != None:
            return cursor + 4
        if re.search(r"^ret", op) != None:
            return cursor + 4
        if re.search(r"^b ", op) != None:
            return cursor + 4
        cursor -= 4

    return min_addr


def carve_trap_num(addr, flag):
    saved_seek = r.cmd("?v $$")
    r.cmd("e io.cache=true")
    r.cmd("e emu.write=true")
    r.cmd("aei")
    r.cmd("aeim")
    min_addr = int(r.cmd(f"?v {flag}"), 0)
    emu_start = walk_back_until(addr - 4, r"^b|^ret|^invalid", min_addr)
    r.cmd(f"s {str(emu_start)}")
    obj = r.cmd("aefa 0x%08x~[0]:0" % addr)
    r.cmd(f"s {saved_seek}")
    val = r.cmdj(f"pv4j @ {obj.strip()}+0x14")[0]["value"]
    if val == 0:
        val = r.cmdj(f"pv4j @ {obj.strip()}+0x18")[0]["value"]
    return val


def beautify_name(name):
    return re.sub(r"^_", "", name)


def carve_traps():
    msgs = r.cmdj("axtj @ sym._mach_msg")
    if len(msgs) == 0:
        r.cmd("s sym._mach_msg")
        r.cmd("aae $SS @ $S")
        r.cmd("shu")
        msgs = r.cmdj("axtj @ sym._mach_msg")
    if len(msgs) == 0:
        print("Cannot find refs to mach_msg!")
        return

    traps = {}
    for ref in msgs:
        if ref["type"] != "CALL" or "realname" not in ref:
            continue
        name = ref["realname"]
        if re.search(r"^_mach_msg", name) != None:
            continue
        addr = ref["from"]
        traps[addr] = {"name": name}

    result = []
    for addr, trap in traps.items():
        flag = f'sym.{trap["name"]}'
        trap["name"] = beautify_name(trap["name"])
        trap["num"] = carve_trap_num(addr, flag)
        if trap["num"] != None:
            result.append(trap)

    result.sort(key=lambda x: x["num"])

    return result


if __name__ == "__main__":
    traps = carve_traps()
    print(json.dumps(traps, indent=4))
