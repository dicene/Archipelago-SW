"""
Animal Well Archipelago Client
Based (read: copied almost wholesale and edited) off the Zelda1 Client.
"""

import asyncio
import os
import platform

import pymem

import Utils
from CommonClient import CommonContext, server_loop, gui_enabled, ClientCommandProcessor, logger, get_base_parser
from NetUtils import ClientStatus
from typing import Dict
from .items import item_name_to_id
from .locations import location_name_to_id, location_table, ByteSect
from .names import ItemNames as iname, LocationNames as lname
from .options import FinalEggLocation, Goal

CONNECTION_ABORTED_STATUS = "Connection Refused. Some unrecoverable error occurred"
CONNECTION_REFUSED_STATUS = "Connection Refused. Please make sure exactly one Animal Well instance is running"
CONNECTION_RESET_STATUS = "Connection was reset. Please wait"
CONNECTION_CONNECTED_STATUS = "Connected"
CONNECTION_TENTATIVE_STATUS = "Connection has been initiated"
CONNECTION_INITIAL_STATUS = "Connection has not been initiated"

HEADER_LENGTH = 0x18
SAVE_SLOT_LENGTH = 0x27010


class AnimalWellCommandProcessor(ClientCommandProcessor):
    """
    CommandProcessor for Animal Well
    """

    def _cmd_connection(self):
        """Check Animal Well Connection State"""
        if isinstance(self.ctx, AnimalWellContext):
            logger.info(f"Animal Well Connection Status: {self.ctx.connection_status}")

    def _cmd_ring(self):
        """Toggles the cheater's ring in your inventory to allow noclip and get unstuck"""
        try:
            if isinstance(self.ctx, AnimalWellContext):
                if self.ctx.process_handle and self.ctx.start_address:
                    if platform.uname()[0] == "Windows":
                        active_slot = self.ctx.get_active_game_slot()
                        slot_address = self.ctx.start_address + HEADER_LENGTH + (SAVE_SLOT_LENGTH * active_slot)

                        # Read Quest State
                        flags = int.from_bytes(self.ctx.process_handle.read_bytes(slot_address + 0x1EC, 4),
                                               byteorder="little")

                        if bool(flags >> 13 & 1):
                            logger.info("Removing C. Ring from inventory")
                        else:
                            logger.info("Adding C. Ring to inventory. Press F to use")

                        bits = ((str(flags >> 0 & 1)) +  # House Opened
                                (str(flags >> 1 & 1)) +  # Office Opened
                                (str(flags >> 2 & 1)) +  # Closet Opened
                                (str(flags >> 3 & 1)) +  # Unknown
                                (str(flags >> 4 & 1)) +  # Unknown
                                (str(flags >> 5 & 1)) +  # Unknown
                                (str(flags >> 6 & 1)) +  # Unknown
                                (str(flags >> 7 & 1)) +  # Unknown
                                (str(flags >> 8 & 1)) +  # Switch State
                                (str(flags >> 9 & 1)) +  # Map Collected
                                (str(flags >> 10 & 1)) +  # Stamps Collected
                                (str(flags >> 11 & 1)) +  # Pencil Collected
                                (str(flags >> 12 & 1)) +  # Chameleon Defeated
                                ("0" if bool(flags >> 13 & 1) else "1") +  # C Ring Collected
                                (str(flags >> 14 & 1)) +  # Eaten By Chameleon
                                (str(flags >> 15 & 1)) +  # Inserted S Medal
                                (str(flags >> 16 & 1)) +  # Inserted E Medal
                                (str(flags >> 17 & 1)) +  # Wings Acquired
                                (str(flags >> 18 & 1)) +  # Woke Up
                                (str(flags >> 19 & 1)) +  # B.B. Wand Upgrade
                                (str(flags >> 20 & 1)) +  # Egg 65 Collected
                                (str(flags >> 21 & 1)) +  # All Candles Lit
                                (str(flags >> 22 & 1)) +  # Singularity Active
                                (str(flags >> 23 & 1)) +  # Manticore Egg Placed
                                (str(flags >> 24 & 1)) +  # Bat Defeated
                                (str(flags >> 25 & 1)) +  # Ostrich Freed
                                (str(flags >> 26 & 1)) +  # Ostrich Defeated
                                (str(flags >> 27 & 1)) +  # Eel Fight Active
                                (str(flags >> 28 & 1)) +  # Eel Defeated
                                (str(flags >> 29 & 1)) +  # No Disc in Shrine
                                (str(flags >> 30 & 1)) +  # No Disk in Statue
                                (str(flags >> 31 & 1)))[::-1]  # Unknown
                        buffer = int(bits, 2).to_bytes((len(bits) + 7) // 8, byteorder="little")
                        self.ctx.process_handle.write_bytes(slot_address + 0x1EC, buffer, 4)
                    else:
                        raise NotImplementedError("Only Windows is implemented right now")
        except pymem.exception.ProcessError as e:
            logger.error("%s", e)
            self.ctx.connection_status = CONNECTION_RESET_STATUS
            logger.info(f"Animal Well Connection Status: {self.ctx.connection_status}")
        except pymem.exception.MemoryReadError as e:
            logger.error("%s", e)
            self.ctx.connection_status = CONNECTION_RESET_STATUS
            logger.info(f"Animal Well Connection Status: {self.ctx.connection_status}")
        except pymem.exception.MemoryWriteError as e:
            logger.error("%s", e)
            self.ctx.connection_status = CONNECTION_RESET_STATUS
            logger.info(f"Animal Well Connection Status: {self.ctx.connection_status}")
        except Exception as e:
            logger.fatal("An unknown error has occurred: %s", e)
            self.ctx.connection_status = CONNECTION_ABORTED_STATUS
            logger.info(f"Animal Well Connection Status: {self.ctx.connection_status}")


class AnimalWellContext(CommonContext):
    """
    Animal Well Archipelago context
    """
    command_processor = AnimalWellCommandProcessor
    items_handling = 0b111  # get sent remote and starting items

    def __init__(self, server_address, password):
        super().__init__(server_address, password)
        self.game = "ANIMAL WELL"
        self.process_sync_task = None
        self.get_animal_well_process_handle_task = None
        self.process_handle = None
        self.start_address = None
        self.connection_status = CONNECTION_INITIAL_STATUS
        self.slot_data = {}
        self.first_m_disc = True
        self.used_firecrackers = 0
        self.used_berries = 0

    async def server_auth(self, password_requested: bool = False):
        """
        Authenticate with the Archipelago server
        """
        if password_requested and not self.password:
            await super(AnimalWellContext, self).server_auth(password_requested)
        await self.get_username()
        await self.send_connect()

    def run_gui(self):
        """
        Run the GUI
        """
        from kvui import GameManager

        class AnimalWellManager(GameManager):
            """
            Animal Well Manager
            """
            logging_pairs = [
                ("Client", "Archipelago")
            ]
            base_title = "Archipelago Animal Well Client"

        self.ui = AnimalWellManager(self)
        self.ui_task = asyncio.create_task(self.ui.async_run(), name="UI")

    def on_package(self, cmd: str, args: dict):
        if cmd == "Connected":
            self.slot_data = args.get("slot_data", {})

    def get_active_game_slot(self) -> int:
        """
        Get the game slot currently being played
        """
        if platform.uname()[0] == "Windows":
            slot = self.process_handle.read_bytes(self.start_address + 0xC, 1)[0]
            if slot == 0:
                raise ConnectionResetError("Slot 1 detected, please be in slot 2 or 3")
            return slot
        else:
            raise NotImplementedError("Only Windows is implemented right now")


class AWLocations:
    """
    The checks the player has found
    """

    def __init__(self):
        self.byte_sect_dict: Dict[int, int] = {}
        self.loc_statuses: Dict[str, bool] = {}
        for loc_name in location_table.keys():
            self.loc_statuses[loc_name] = False

    def read_from_game(self, ctx):
        """
        Read checked locations from the process
        """
        try:
            if platform.uname()[0] == "Windows":
                active_slot = ctx.get_active_game_slot()
                slot_address = ctx.start_address + HEADER_LENGTH + (SAVE_SLOT_LENGTH * active_slot)

                self.byte_sect_dict: Dict[int, int] = {
                    ByteSect.items.value:
                        int.from_bytes(ctx.process_handle.read_bytes(slot_address + 0x120, 16), byteorder="little"),
                    ByteSect.bunnies.value:
                        int.from_bytes(ctx.process_handle.read_bytes(slot_address + 0x198, 4), byteorder="little"),
                    ByteSect.candles.value:
                        int.from_bytes(ctx.process_handle.read_bytes(slot_address + 0x1E0, 2), byteorder="little"),
                    ByteSect.house_key.value:
                        int.from_bytes(ctx.process_handle.read_bytes(slot_address + 0x21C, 2), byteorder="little")
                }

                for loc_name, status in self.loc_statuses.items():
                    loc_data = location_table[loc_name]

                    if loc_data.byte_section == ByteSect.flames:
                        self.loc_statuses[loc_name] = (
                                ctx.process_handle.read_bytes(slot_address + loc_data.byte_offset, 1)[0] >= 4)
                        continue

                    self.loc_statuses[loc_name] = (
                        bool(self.byte_sect_dict[loc_data.byte_section] >> loc_data.byte_offset & 1))
            else:
                raise NotImplementedError("Only Windows is implemented right now")
        except pymem.exception.ProcessError as e:
            logger.error("%s", e)
            ctx.connection_status = CONNECTION_RESET_STATUS
            logger.info(f"Animal Well Connection Status: {ctx.connection_status}")
        except pymem.exception.MemoryReadError as e:
            logger.error("%s", e)
            ctx.connection_status = CONNECTION_RESET_STATUS
            logger.info(f"Animal Well Connection Status: {ctx.connection_status}")
        except ConnectionResetError as e:
            logger.error("%s", e)
            ctx.connection_status = CONNECTION_RESET_STATUS
            logger.info(f"Animal Well Connection Status: {ctx.connection_status}")
        except NotImplementedError as e:
            logger.fatal("%s", e)
            ctx.connection_status = CONNECTION_ABORTED_STATUS
            logger.info(f"Animal Well Connection Status: {ctx.connection_status}")
        except Exception as e:
            logger.fatal("An unknown error has occurred: %s", e)
            ctx.connection_status = CONNECTION_ABORTED_STATUS
            logger.info(f"Animal Well Connection Status: {ctx.connection_status}")

    async def write_to_archipelago(self, ctx):
        """
        Write checked locations to archipelago
        """
        try:
            for loc_name, status in self.loc_statuses.items():
                if status:
                    ctx.locations_checked.add(location_name_to_id[loc_name])

            if "goal" not in ctx.slot_data or ctx.slot_data["goal"] == Goal.option_fireworks:
                if not ctx.finished_game and self.loc_statuses[lname.key_house]:
                    await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
                    ctx.finished_game = True

            locations_checked = []
            for location in ctx.missing_locations:
                if location in ctx.locations_checked:
                    locations_checked.append(location)
            if locations_checked:
                await ctx.send_msgs([
                    {"cmd": "LocationChecks",
                     "locations": locations_checked}
                ])
        except Exception as e:
            logger.fatal("An unknown error has occurred: %s", e)
            ctx.connection_status = CONNECTION_ABORTED_STATUS
            logger.info(f"Animal Well Connection Status: {ctx.connection_status}")


class AWItems:
    """
    The items the player has received
    """

    def __init__(self):
        # Major progression items
        self.bubble = 0  # progressive
        # self.disc = False
        self.yoyo = False
        self.slink = False
        self.flute = False
        self.top = False
        self.lantern = False
        self.uv = False
        self.ball = False
        self.remote = False
        self.wheel = False
        self.firecrackers = True

        # Minor progression items and keys
        self.m_disc = False
        self.fanny_pack = False

        self.match = 0
        self.matchbox = False

        self.key = 0
        self.key_ring = False
        self.house_key = False
        self.office_key = False

        self.e_medal = False
        self.s_medal = False
        self.k_shard = 0

        # self.blue_flame = False
        # self.green_flame = False
        # self.violet_flame = False
        # self.pink_flame = False

        # Eggs
        self.egg_reference = False
        self.egg_brown = False
        self.egg_raw = False
        self.egg_pickled = False
        self.egg_big = False
        self.egg_swan = False
        self.egg_forbidden = False
        self.egg_shadow = False
        self.egg_vanity = False
        self.egg_service = False

        self.egg_depraved = False
        self.egg_chaos = False
        self.egg_upside_down = False
        self.egg_evil = False
        self.egg_sweet = False
        self.egg_chocolate = False
        self.egg_value = False
        self.egg_plant = False
        self.egg_red = False
        self.egg_orange = False
        self.egg_sour = False
        self.egg_post_modern = False

        self.egg_universal = False
        self.egg_lf = False
        self.egg_zen = False
        self.egg_future = False
        self.egg_friendship = False
        self.egg_truth = False
        self.egg_transcendental = False
        self.egg_ancient = False
        self.egg_magic = False
        self.egg_mystic = False
        self.egg_holiday = False
        self.egg_rain = False
        self.egg_razzle = False
        self.egg_dazzle = False

        self.egg_virtual = False
        self.egg_normal = False
        self.egg_great = False
        self.egg_gorgeous = False
        self.egg_planet = False
        self.egg_moon = False
        self.egg_galaxy = False
        self.egg_sunset = False
        self.egg_goodnight = False
        self.egg_dream = False
        self.egg_travel = False
        self.egg_promise = False
        self.egg_ice = False
        self.egg_fire = False

        self.egg_bubble = False
        self.egg_desert = False
        self.egg_clover = False
        self.egg_brick = False
        self.egg_neon = False
        self.egg_iridescent = False
        self.egg_rust = False
        self.egg_scarlet = False
        self.egg_sapphire = False
        self.egg_ruby = False
        self.egg_jade = False
        self.egg_obsidian = False
        self.egg_crystal = False
        self.egg_golden = False

        self.egg_65 = False

        self.firecracker_refill = 0
        self.big_blue_fruit = 0

    async def read_from_archipelago(self, ctx):
        """
        Read inventory state from archipelago
        """
        try:
            items = [item.item for item in ctx.items_received]

            # Major progression items
            self.bubble = len([item for item in items if item == item_name_to_id[iname.bubble.value]])
            # self.disc = item_name_to_id[iname.disc.value] in items
            self.yoyo = item_name_to_id[iname.yoyo.value] in items
            self.slink = item_name_to_id[iname.slink.value] in items
            self.flute = item_name_to_id[iname.flute.value] in items
            self.top = item_name_to_id[iname.top.value] in items
            self.lantern = item_name_to_id[iname.lantern.value] in items
            self.uv = item_name_to_id[iname.uv.value] in items
            self.ball = item_name_to_id[iname.ball.value] in items
            self.remote = item_name_to_id[iname.remote.value] in items
            self.wheel = item_name_to_id[iname.wheel.value] in items
            self.firecrackers = item_name_to_id[iname.firecrackers.value] in items

            # Minor progression items and keys
            self.m_disc = item_name_to_id[iname.m_disc.value] in items
            self.fanny_pack = item_name_to_id[iname.fanny_pack.value] in items

            self.match = len([item for item in items if item == item_name_to_id[iname.match.value]])
            self.matchbox = item_name_to_id[iname.matchbox.value] in items

            self.key = len([item for item in items if item == item_name_to_id[iname.key.value]])
            self.key_ring = item_name_to_id[iname.key_ring.value] in items
            self.house_key = item_name_to_id[iname.house_key.value] in items
            self.office_key = item_name_to_id[iname.office_key.value] in items

            self.e_medal = item_name_to_id[iname.e_medal.value] in items
            self.s_medal = item_name_to_id[iname.s_medal.value] in items
            self.k_shard = len([item for item in items if item == item_name_to_id[iname.k_shard.value]])

            # self.blue_flame = item_name_to_id[iname.blue_flame.value] in items
            # self.green_flame = item_name_to_id[iname.green_flame.value] in items
            # self.violet_flame = item_name_to_id[iname.violet_flame.value] in items
            # self.pink_flame = item_name_to_id[iname.pink_flame.value] in items

            # Eggs
            self.egg_reference = item_name_to_id[iname.egg_reference.value] in items
            self.egg_brown = item_name_to_id[iname.egg_brown.value] in items
            self.egg_raw = item_name_to_id[iname.egg_raw.value] in items
            self.egg_pickled = item_name_to_id[iname.egg_pickled.value] in items
            self.egg_big = item_name_to_id[iname.egg_big.value] in items
            self.egg_swan = item_name_to_id[iname.egg_swan.value] in items
            self.egg_forbidden = item_name_to_id[iname.egg_forbidden.value] in items
            self.egg_shadow = item_name_to_id[iname.egg_shadow.value] in items
            self.egg_vanity = item_name_to_id[iname.egg_vanity.value] in items
            self.egg_service = item_name_to_id[iname.egg_service.value] in items

            self.egg_depraved = item_name_to_id[iname.egg_depraved.value] in items
            self.egg_chaos = item_name_to_id[iname.egg_chaos.value] in items
            self.egg_upside_down = item_name_to_id[iname.egg_upside_down.value] in items
            self.egg_evil = item_name_to_id[iname.egg_evil.value] in items
            self.egg_sweet = item_name_to_id[iname.egg_sweet.value] in items
            self.egg_chocolate = item_name_to_id[iname.egg_chocolate.value] in items
            self.egg_value = item_name_to_id[iname.egg_value.value] in items
            self.egg_plant = item_name_to_id[iname.egg_plant.value] in items
            self.egg_red = item_name_to_id[iname.egg_red.value] in items
            self.egg_orange = item_name_to_id[iname.egg_orange.value] in items
            self.egg_sour = item_name_to_id[iname.egg_sour.value] in items
            self.egg_post_modern = item_name_to_id[iname.egg_post_modern.value] in items

            self.egg_universal = item_name_to_id[iname.egg_universal.value] in items
            self.egg_lf = item_name_to_id[iname.egg_lf.value] in items
            self.egg_zen = item_name_to_id[iname.egg_zen.value] in items
            self.egg_future = item_name_to_id[iname.egg_future.value] in items
            self.egg_friendship = item_name_to_id[iname.egg_friendship.value] in items
            self.egg_truth = item_name_to_id[iname.egg_truth.value] in items
            self.egg_transcendental = item_name_to_id[iname.egg_transcendental.value] in items
            self.egg_ancient = item_name_to_id[iname.egg_ancient.value] in items
            self.egg_magic = item_name_to_id[iname.egg_magic.value] in items
            self.egg_mystic = item_name_to_id[iname.egg_mystic.value] in items
            self.egg_holiday = item_name_to_id[iname.egg_holiday.value] in items
            self.egg_rain = item_name_to_id[iname.egg_rain.value] in items
            self.egg_razzle = item_name_to_id[iname.egg_razzle.value] in items
            self.egg_dazzle = item_name_to_id[iname.egg_dazzle.value] in items

            self.egg_virtual = item_name_to_id[iname.egg_virtual.value] in items
            self.egg_normal = item_name_to_id[iname.egg_normal.value] in items
            self.egg_great = item_name_to_id[iname.egg_great.value] in items
            self.egg_gorgeous = item_name_to_id[iname.egg_gorgeous.value] in items
            self.egg_planet = item_name_to_id[iname.egg_planet.value] in items
            self.egg_moon = item_name_to_id[iname.egg_moon.value] in items
            self.egg_galaxy = item_name_to_id[iname.egg_galaxy.value] in items
            self.egg_sunset = item_name_to_id[iname.egg_sunset.value] in items
            self.egg_goodnight = item_name_to_id[iname.egg_goodnight.value] in items
            self.egg_dream = item_name_to_id[iname.egg_dream.value] in items
            self.egg_travel = item_name_to_id[iname.egg_travel.value] in items
            self.egg_promise = item_name_to_id[iname.egg_promise.value] in items
            self.egg_ice = item_name_to_id[iname.egg_ice.value] in items
            self.egg_fire = item_name_to_id[iname.egg_fire.value] in items

            self.egg_bubble = item_name_to_id[iname.egg_bubble.value] in items
            self.egg_desert = item_name_to_id[iname.egg_desert.value] in items
            self.egg_clover = item_name_to_id[iname.egg_clover.value] in items
            self.egg_brick = item_name_to_id[iname.egg_brick.value] in items
            self.egg_neon = item_name_to_id[iname.egg_neon.value] in items
            self.egg_iridescent = item_name_to_id[iname.egg_iridescent.value] in items
            self.egg_rust = item_name_to_id[iname.egg_rust.value] in items
            self.egg_scarlet = item_name_to_id[iname.egg_scarlet.value] in items
            self.egg_sapphire = item_name_to_id[iname.egg_sapphire.value] in items
            self.egg_ruby = item_name_to_id[iname.egg_ruby.value] in items
            self.egg_jade = item_name_to_id[iname.egg_jade.value] in items
            self.egg_obsidian = item_name_to_id[iname.egg_obsidian.value] in items
            self.egg_crystal = item_name_to_id[iname.egg_crystal.value] in items
            self.egg_golden = item_name_to_id[iname.egg_golden.value] in items

            # todo: fix this
            if "goal" in ctx.slot_data and ctx.slot_data["goal"] == Goal.option_egg_hunt:
                if (not ctx.finished_game and
                        self.egg_reference and self.egg_brown and self.egg_raw and self.egg_pickled and
                        self.egg_big and self.egg_swan and self.egg_forbidden and self.egg_shadow and
                        self.egg_vanity and self.egg_service and self.egg_depraved and self.egg_chaos and
                        self.egg_upside_down and self.egg_evil and self.egg_sweet and self.egg_chocolate and
                        self.egg_value and self.egg_plant and self.egg_red and self.egg_orange and
                        self.egg_sour and self.egg_post_modern and self.egg_universal and self.egg_lf and
                        self.egg_zen and self.egg_future and self.egg_friendship and self.egg_truth and
                        self.egg_transcendental and self.egg_ancient and self.egg_magic and self.egg_mystic and
                        self.egg_holiday and self.egg_rain and self.egg_razzle and self.egg_dazzle and
                        self.egg_virtual and self.egg_normal and self.egg_great and self.egg_gorgeous and
                        self.egg_planet and self.egg_moon and self.egg_galaxy and self.egg_sunset and
                        self.egg_goodnight and self.egg_dream and self.egg_travel and self.egg_promise and
                        self.egg_ice and self.egg_fire and self.egg_bubble and self.egg_desert and
                        self.egg_clover and self.egg_brick and self.egg_neon and self.egg_iridescent and
                        self.egg_rust and self.egg_scarlet and self.egg_sapphire and self.egg_ruby and
                        self.egg_jade and self.egg_obsidian and self.egg_crystal and self.egg_golden):
                    await ctx.send_msgs([{"cmd": "StatusUpdate", "status": ClientStatus.CLIENT_GOAL}])
                    ctx.finished_game = True

            self.egg_65 = item_name_to_id[iname.egg_65.value] in items

            self.firecracker_refill = len([item for item in items if item == item_name_to_id["Firecracker Refill"]])
            self.big_blue_fruit = len([item for item in items if item == item_name_to_id["Big Blue Fruit"]])
        except Exception as e:
            logger.fatal("An unknown error has occurred: %s", e)
            ctx.connection_status = CONNECTION_ABORTED_STATUS
            logger.info(f"Animal Well Connection Status: {ctx.connection_status}")

    def write_to_game(self, ctx):
        """
        Write inventory state to the process
        """
        try:
            if platform.uname()[0] == "Windows":
                active_slot = ctx.get_active_game_slot()
                slot_address = ctx.start_address + HEADER_LENGTH + (SAVE_SLOT_LENGTH * active_slot)

                # Read Quest State
                flags = int.from_bytes(ctx.process_handle.read_bytes(slot_address + 0x1EC, 4), byteorder="little")
                inserted_s_medal = bool(flags >> 15 & 1)
                inserted_e_medal = bool(flags >> 16 & 1)

                # Write Quest State
                egg_65 = self.egg_65
                if (FinalEggLocation.internal_name not in ctx.slot_data
                        or not ctx.slot_data[FinalEggLocation.internal_name]):
                    egg_65 = bool(flags >> 20 & 1)

                bits = ((str(flags >> 0 & 1)) +  # House Opened
                        (str(flags >> 1 & 1)) +  # Office Opened
                        (str(flags >> 2 & 1)) +  # Closet Opened
                        (str(flags >> 3 & 1)) +  # Unknown
                        (str(flags >> 4 & 1)) +  # Unknown
                        (str(flags >> 5 & 1)) +  # Unknown
                        (str(flags >> 6 & 1)) +  # Unknown
                        (str(flags >> 7 & 1)) +  # Unknown
                        (str(flags >> 8 & 1)) +  # Switch State
                        "1" +  # Map Collected
                        "1" +  # Stamps Collected
                        "1" +  # Pencil Collected
                        (str(flags >> 12 & 1)) +  # Chameleon Defeated
                        (str(flags >> 13 & 1)) +  # C Ring Collected
                        (str(flags >> 14 & 1)) +  # Eaten By Chameleon
                        ("1" if inserted_s_medal else "0") +  # Inserted S Medal
                        ("1" if inserted_e_medal else "0") +  # Inserted E Medal
                        (str(flags >> 17 & 1)) +  # Wings Acquired
                        (str(flags >> 18 & 1)) +  # Woke Up
                        ("1" if self.bubble > 1 else "0") +  # B.B. Wand Upgrade
                        ("1" if egg_65 else "0") +  # Egg 65 Collected
                        (str(flags >> 21 & 1)) +  # All Candles Lit
                        (str(flags >> 22 & 1)) +  # Singularity Active
                        (str(flags >> 23 & 1)) +  # Manticore Egg Placed
                        (str(flags >> 24 & 1)) +  # Bat Defeated
                        (str(flags >> 25 & 1)) +  # Ostrich Freed
                        (str(flags >> 26 & 1)) +  # Ostrich Defeated
                        (str(flags >> 27 & 1)) +  # Eel Fight Active
                        (str(flags >> 28 & 1)) +  # Eel Defeated
                        (str(flags >> 29 & 1)) +  # No Disc in Shrine
                        (str(flags >> 30 & 1)) +  # No Disk in Statue
                        (str(flags >> 31 & 1)))[::-1]  # Unknown
                buffer = int(bits, 2).to_bytes((len(bits) + 7) // 8, byteorder="little")
                ctx.process_handle.write_bytes(slot_address + 0x1EC, buffer, 4)

                # Write Eggs
                bits = (("1" if self.egg_reference else "0") +
                        ("1" if self.egg_brown else "0") +
                        ("1" if self.egg_raw else "0") +
                        ("1" if self.egg_pickled else "0") +
                        ("1" if self.egg_big else "0") +
                        ("1" if self.egg_swan else "0") +
                        ("1" if self.egg_forbidden else "0") +
                        ("1" if self.egg_shadow else "0") +

                        ("1" if self.egg_vanity else "0") +
                        ("1" if self.egg_service else "0") +
                        ("1" if self.egg_depraved else "0") +
                        ("1" if self.egg_chaos else "0") +
                        ("1" if self.egg_upside_down else "0") +
                        ("1" if self.egg_evil else "0") +
                        ("1" if self.egg_sweet else "0") +
                        ("1" if self.egg_chocolate else "0") +

                        ("1" if self.egg_value else "0") +
                        ("1" if self.egg_plant else "0") +
                        ("1" if self.egg_red else "0") +
                        ("1" if self.egg_orange else "0") +
                        ("1" if self.egg_sour else "0") +
                        ("1" if self.egg_post_modern else "0") +
                        ("1" if self.egg_universal else "0") +
                        ("1" if self.egg_lf else "0") +

                        ("1" if self.egg_zen else "0") +
                        ("1" if self.egg_future else "0") +
                        ("1" if self.egg_friendship else "0") +
                        ("1" if self.egg_truth else "0") +
                        ("1" if self.egg_transcendental else "0") +
                        ("1" if self.egg_ancient else "0") +
                        ("1" if self.egg_magic else "0") +
                        ("1" if self.egg_mystic else "0") +

                        ("1" if self.egg_holiday else "0") +
                        ("1" if self.egg_rain else "0") +
                        ("1" if self.egg_razzle else "0") +
                        ("1" if self.egg_dazzle else "0") +
                        ("1" if self.egg_virtual else "0") +
                        ("1" if self.egg_normal else "0") +
                        ("1" if self.egg_great else "0") +
                        ("1" if self.egg_gorgeous else "0") +

                        ("1" if self.egg_planet else "0") +
                        ("1" if self.egg_moon else "0") +
                        ("1" if self.egg_galaxy else "0") +
                        ("1" if self.egg_sunset else "0") +
                        ("1" if self.egg_goodnight else "0") +
                        ("1" if self.egg_dream else "0") +
                        ("1" if self.egg_travel else "0") +
                        ("1" if self.egg_promise else "0") +

                        ("1" if self.egg_ice else "0") +
                        ("1" if self.egg_fire else "0") +
                        ("1" if self.egg_bubble else "0") +
                        ("1" if self.egg_desert else "0") +
                        ("1" if self.egg_clover else "0") +
                        ("1" if self.egg_brick else "0") +
                        ("1" if self.egg_neon else "0") +
                        ("1" if self.egg_iridescent else "0") +

                        ("1" if self.egg_rust else "0") +
                        ("1" if self.egg_scarlet else "0") +
                        ("1" if self.egg_sapphire else "0") +
                        ("1" if self.egg_ruby else "0") +
                        ("1" if self.egg_jade else "0") +
                        ("1" if self.egg_obsidian else "0") +
                        ("1" if self.egg_crystal else "0") +
                        ("1" if self.egg_golden else "0"))[::-1]
                buffer = int(bits, 2).to_bytes((len(bits) + 7) // 8, byteorder="little")
                ctx.process_handle.write_bytes(slot_address + 0x188, buffer, 8)

                # Read Opened Doors
                keys_used = ctx.process_handle.read_bytes(slot_address + 0x1AA, 1)[0]

                # Write Keys
                if self.key_ring:
                    buffer = bytes([1])
                else:
                    buffer = bytes([max(0, self.key - keys_used)])
                ctx.process_handle.write_bytes(slot_address + 0x1B1, buffer, 1)

                # Read Candles Lit
                flags = int.from_bytes(ctx.process_handle.read_bytes(slot_address + 0x1E0, 2), byteorder="little")
                candles_lit = ((flags >> 0 & 1) +
                               (flags >> 1 & 1) +
                               (flags >> 2 & 1) +
                               (flags >> 3 & 1) +
                               (flags >> 4 & 1) +
                               (flags >> 5 & 1) +
                               (flags >> 6 & 1) +
                               (flags >> 7 & 1) +

                               (flags >> 8 & 1))

                # Write Matches
                if self.matchbox:
                    buffer = bytes([1])
                else:
                    buffer = bytes([max(0, self.match - candles_lit)])
                ctx.process_handle.write_bytes(slot_address + 0x1B2, buffer, 1)

                # Read Owned Equipment
                flags = int.from_bytes(ctx.process_handle.read_bytes(slot_address + 0x1DC, 2), byteorder="little")
                disc = bool(flags >> 5 & 1)

                # Write Owned Equipment
                bits = ((str(flags >> 0 & 1)) +  # Unknown
                        ("1" if self.firecrackers else "0") +
                        ("1" if self.flute else "0") +
                        ("1" if self.lantern else "0") +
                        ("1" if self.top else "0") +
                        ("1" if disc else "0") +
                        ("1" if self.bubble > 0 else "0") +
                        ("1" if self.yoyo else "0") +

                        ("1" if self.slink else "0") +
                        ("1" if self.remote else "0") +
                        ("1" if self.ball else "0") +
                        ("1" if self.wheel else "0") +
                        ("1" if self.uv else "0") +
                        (str(flags >> 13 & 1)) +  # Pad
                        (str(flags >> 14 & 1)) +  # Pad
                        (str(flags >> 15 & 1)))[::-1]  # Pad
                buffer = int(bits, 2).to_bytes((len(bits) + 7) // 8, byteorder="little")
                ctx.process_handle.write_bytes(slot_address + 0x1DC, buffer, 2)

                # Read Other Items
                flags = int.from_bytes(ctx.process_handle.read_bytes(slot_address + 0x1DE, 1), byteorder="little")
                possess_m_disc = self.m_disc and (bool(flags >> 0 & 1) or ctx.first_m_disc)
                if self.m_disc:
                    ctx.first_m_disc = False

                # Write Other Items
                bits = (("1" if possess_m_disc else "0") +  # Mock Disc
                        ("1" if (self.s_medal and not inserted_s_medal) else "0") +  # S Medal
                        (str(flags >> 2 & 1)) +  # Unused
                        ("1" if self.house_key else "0") +  # House Key
                        ("1" if self.office_key else "0") +  # Office Key
                        (str(flags >> 5 & 1)) +  # Unused
                        ("1" if (self.e_medal and not inserted_e_medal) else "0") +  # E Medal
                        ("1" if self.fanny_pack else "0"))[::-1]  # Fanny Pack
                buffer = int(bits, 2).to_bytes((len(bits) + 7) // 8, byteorder="little")
                ctx.process_handle.write_bytes(slot_address + 0x1DE, buffer, 1)

                # Read K Shards
                k_shard_1 = bytes([0])
                if self.k_shard >= 1:
                    k_shard_1 = bytes([max(2, ctx.process_handle.read_bytes(slot_address + 0x1FE, 1)[0])])
                k_shard_2 = bytes([0])
                if self.k_shard >= 2:
                    k_shard_2 = bytes([max(2, ctx.process_handle.read_bytes(slot_address + 0x20A, 1)[0])])
                k_shard_3 = bytes([0])
                if self.k_shard >= 3:
                    k_shard_3 = bytes([max(2, ctx.process_handle.read_bytes(slot_address + 0x216, 1)[0])])

                # Write K Shards
                ctx.process_handle.write_bytes(slot_address + 0x1FE, k_shard_1, 1)
                ctx.process_handle.write_bytes(slot_address + 0x20A, k_shard_2, 1)
                ctx.process_handle.write_bytes(slot_address + 0x216, k_shard_3, 1)

                # Berries
                berries_to_use = self.big_blue_fruit - ctx.used_berries
                total_hearts = int.from_bytes(ctx.process_handle.read_bytes(slot_address + 0x1B4, 1),
                                              byteorder="little")
                total_hearts = min(total_hearts + berries_to_use, 255)
                buffer = bytes([total_hearts])
                ctx.process_handle.write_bytes(slot_address + 0x1B4, buffer, 1)
                ctx.used_berries = self.big_blue_fruit

                # Firecrackers
                firecrackers_to_use = self.firecracker_refill - ctx.used_firecrackers
                total_firecrackers = int.from_bytes(ctx.process_handle.read_bytes(slot_address + 0x1B3, 1),
                                                    byteorder="little")
                total_firecrackers = min(total_firecrackers + firecrackers_to_use, 6 if self.fanny_pack else 3)
                buffer = bytes([total_firecrackers])
                ctx.process_handle.write_bytes(slot_address + 0x1B3, buffer, 1)
                ctx.used_firecrackers = self.firecracker_refill

                # setting death count to 37 to always have the b.b. wand chest accessible
                buffer = 37
                buffer = buffer.to_bytes(2, byteorder="little")
                ctx.process_handle.write_bytes(slot_address + 0x1E4, buffer, 2)
            else:
                raise NotImplementedError("Only Windows is implemented right now")
        except pymem.exception.ProcessError as e:
            logger.error("%s", e)
            ctx.connection_status = CONNECTION_RESET_STATUS
            logger.info(f"Animal Well Connection Status: {ctx.connection_status}")
        except pymem.exception.MemoryReadError as e:
            logger.error("%s", e)
            ctx.connection_status = CONNECTION_RESET_STATUS
            logger.info(f"Animal Well Connection Status: {ctx.connection_status}")
        except pymem.exception.MemoryWriteError as e:
            logger.error("%s", e)
            ctx.connection_status = CONNECTION_RESET_STATUS
            logger.info(f"Animal Well Connection Status: {ctx.connection_status}")
        except ConnectionResetError as e:
            logger.error("%s", e)
            ctx.connection_status = CONNECTION_RESET_STATUS
            logger.info(f"Animal Well Connection Status: {ctx.connection_status}")
        except NotImplementedError as e:
            logger.fatal("%s", e)
            ctx.connection_status = CONNECTION_ABORTED_STATUS
            logger.info(f"Animal Well Connection Status: {ctx.connection_status}")
        except Exception as e:
            logger.fatal("An unknown error has occurred: %s", e)
            ctx.connection_status = CONNECTION_ABORTED_STATUS
            logger.info(f"Animal Well Connection Status: {ctx.connection_status}")


async def get_animal_well_process_handle(ctx: AnimalWellContext):
    """
    Get the process handle of Animal Well
    """
    try:
        if platform.uname()[0] == "Windows":
            logger.debug("Getting process handle on Windows")
            process_handle = pymem.Pymem("Animal Well.exe")
            logger.debug("Found PID %d", process_handle.process_id)

            savefile_location = \
                rf"C:\Users\{os.getenv('USERNAME')}\AppData\LocalLow\Billy Basso\Animal Well\AnimalWell.sav"
            logger.debug("Reading save file data from default location: %s", savefile_location)
            with open(savefile_location, "rb") as savefile:
                slot_1 = bytearray(savefile.read(HEADER_LENGTH + SAVE_SLOT_LENGTH))[HEADER_LENGTH:]

            # Find best pattern
            consecutive_start = 0
            max_length = 0
            current_length = 0
            for i in range(len(slot_1)):
                current_length += 1
                if slot_1[i] == 0:
                    current_length = 0
                elif current_length > max_length:
                    max_length = current_length
                    consecutive_start = i - current_length + 1
            pattern = slot_1[consecutive_start: consecutive_start + max_length]
            logger.debug("Found the longest nonzero consecutive memory at %s of length %s", hex(consecutive_start),
                         hex(max_length))

            # Preprocess
            m = len(pattern)
            bad_chars = [-1] * 256
            for i in range(m):
                bad_chars[pattern[i]] = i

            # Search
            address = 0
            iterations = 0
            while True:
                try:
                    iterations += 1
                    if iterations % 0x10000 == 0:
                        await asyncio.sleep(0.05)
                    if iterations % 0x80000 == 0:
                        logger.info("Looking for start address of memory, %s", hex(address))

                    i = m - 1

                    while i >= 0 and pattern[i] == process_handle.read_bytes(address + i, 1)[0]:
                        i -= 1

                    if i < 0:
                        address -= (HEADER_LENGTH + consecutive_start)
                        break
                    else:
                        address += max(1, i - bad_chars[process_handle.read_bytes(address + i, 1)[0]])
                except pymem.exception.MemoryReadError:
                    address += max_length

            logger.info("Found start address of memory, %s", hex(address))

            # Verify
            version = process_handle.read_uint(address)
            logger.debug("Found version number %d", version)

            if version != 9:
                raise NotImplementedError("Animal Well version %d detected, only version 9 supported", version)

            ctx.process_handle = process_handle
            ctx.start_address = address
        else:
            raise NotImplementedError("Only Windows is implemented right now")
    except pymem.exception.ProcessNotFound as e:
        logger.error("%s", e)
        ctx.connection_status = CONNECTION_REFUSED_STATUS
        logger.info(f"Animal Well Connection Status: {ctx.connection_status}")
    except pymem.exception.CouldNotOpenProcess as e:
        logger.error("%s", e)
        ctx.connection_status = CONNECTION_REFUSED_STATUS
        logger.info(f"Animal Well Connection Status: {ctx.connection_status}")
    except pymem.exception.ProcessError as e:
        logger.error("%s", e)
        ctx.connection_status = CONNECTION_REFUSED_STATUS
        logger.info(f"Animal Well Connection Status: {ctx.connection_status}")
    except pymem.exception.MemoryReadError as e:
        logger.error("%s", e)
        ctx.connection_status = CONNECTION_REFUSED_STATUS
        logger.info(f"Animal Well Connection Status: {ctx.connection_status}")
    except FileNotFoundError as e:
        logger.fatal("%s", e)
        ctx.connection_status = CONNECTION_ABORTED_STATUS
        logger.info(f"Animal Well Connection Status: {ctx.connection_status}")
    except NotImplementedError as e:
        logger.fatal("%s", e)
        ctx.connection_status = CONNECTION_ABORTED_STATUS
        logger.info(f"Animal Well Connection Status: {ctx.connection_status}")
    except Exception as e:
        logger.fatal("An unknown error has occurred: %s", e)
        ctx.connection_status = CONNECTION_ABORTED_STATUS
        logger.info(f"Animal Well Connection Status: {ctx.connection_status}")


async def process_sync_task(ctx: AnimalWellContext):
    """
    Connect to the Animal Well process
    """
    logger.info("Starting Animal Well connector. Use /connection for status information")
    locations = AWLocations()
    items = AWItems()

    while not ctx.exit_event.is_set():
        if ctx.connection_status == CONNECTION_ABORTED_STATUS:
            return

        elif ctx.connection_status in [CONNECTION_REFUSED_STATUS, CONNECTION_RESET_STATUS]:
            await asyncio.sleep(5)
            logger.info("Attempting to reconnect to Animal Well")
            if ctx.get_animal_well_process_handle_task:
                ctx.get_animal_well_process_handle_task.cancel()
            ctx.get_animal_well_process_handle_task = asyncio.create_task(get_animal_well_process_handle(ctx))
            ctx.connection_status = CONNECTION_TENTATIVE_STATUS
            logger.info(f"Animal Well Connection Status: {ctx.connection_status}")

        elif ctx.get_animal_well_process_handle_task is None and ctx.connection_status == CONNECTION_INITIAL_STATUS:
            logger.info("Attempting to connect to Animal Well")
            ctx.get_animal_well_process_handle_task = asyncio.create_task(get_animal_well_process_handle(ctx))
            ctx.connection_status = CONNECTION_TENTATIVE_STATUS
            logger.info(f"Animal Well Connection Status: {ctx.connection_status}")

        elif ctx.process_handle and ctx.start_address and ctx.get_animal_well_process_handle_task.done():
            if ctx.connection_status == CONNECTION_TENTATIVE_STATUS:
                logger.info("Successfully Connected to Animal Well")
                ctx.connection_status = CONNECTION_CONNECTED_STATUS
                logger.info(f"Animal Well Connection Status: {ctx.connection_status}")

            locations.read_from_game(ctx)
            await locations.write_to_archipelago(ctx)
            await items.read_from_archipelago(ctx)
            items.write_to_game(ctx)
        await asyncio.sleep(0.1)


def launch():
    """
    Launch the client
    """

    async def main():
        """
        main function
        """
        parser = get_base_parser()
        args = parser.parse_args()

        ctx = AnimalWellContext(args.connect, args.password)
        ctx.server_task = asyncio.create_task(server_loop(ctx), name="ServerLoop")

        if gui_enabled:
            ctx.run_gui()
        ctx.run_cli()

        ctx.process_sync_task = asyncio.create_task(process_sync_task(ctx), name="Animal Well Process Sync")

        await ctx.exit_event.wait()
        ctx.server_address = None
        await ctx.shutdown()

        if ctx.process_sync_task:
            ctx.process_sync_task.cancel()
            ctx.process_sync_task = None
        if ctx.get_animal_well_process_handle_task:
            ctx.get_animal_well_process_handle_task.cancel()
            ctx.get_animal_well_process_handle_task = None

    Utils.init_logging("AnimalWellClient")

    import colorama
    colorama.init()
    asyncio.run(main())
    colorama.deinit()