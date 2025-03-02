from collections.abc import Mapping
from typing import Union

import bson.errors
import pymongo
from datetime import datetime

from pymongo.errors import DuplicateKeyError
from pymongo.synchronous.database import Database
from bson.objectid import ObjectId

from electricall_bills_exceptions import *


_DAY_DEFAULT = 100
_NIGHT_DEFAULT = 80


class ElectricalBills:
    def __init__(self, db: Database):
        self.meters_data = db['meters_data']
        self.meters_data.create_index([("date_time", pymongo.DESCENDING)])
        self.tariff_history = db['tariff_history']
        self.tariff_history.create_index([("date_time", pymongo.DESCENDING)])
        self.meters = db["meters"]
        self.meters.create_index("meter_id", unique=True)
        self.general_data = db["general_data"]

    @staticmethod
    def __are_dict_values_positive(dict_: dict):
        return all(value >= 0 if isinstance(value, (int, float, tuple)) else True for value in dict_.values())

    def add_meter_data(self, meter_id: int, day: float, night: float):
        meter_insert = {"meter_id": meter_id, "day": day, "night": night, "date_time": datetime.now()}

        if not ElectricalBills.__are_dict_values_positive(meter_insert):
            raise NegativeValuesError(f"Negative value/values was/were encountered in new meter data")

        if not self.meters.find_one({"meter_id": meter_id}):
            raise MeterIdNotFoundError(f"There's no meter with id {meter_id}")

        tariff = self.__general_data_get("current_tariff")
        if not tariff:
            raise TariffIsNotSetError("No tariff is set")

        meter_insert["tariff"] = tariff
        last_meters_data = self.__general_data_get("last_meters_data")

        if not last_meters_data:
            cost = tariff["day_tariff"] * day + tariff["night_tariff"] * night
            meter_insert["cost"] = cost
            self.meters_data.insert_one(meter_insert)
            self.__general_data_update("last_meters_data", meter_insert)
            return cost, False

        fake = False
        if last_meters_data["day"] > meter_insert["day"]:
            fake = True
            meter_insert["day"] = last_meters_data["day"] + _DAY_DEFAULT

        if last_meters_data["night"] > meter_insert["night"]:
            fake = True
            meter_insert["night"] = last_meters_data["night"] + _NIGHT_DEFAULT

        cost = (tariff["day_tariff"] * (meter_insert["day"] - last_meters_data["day"]) +
                tariff["night_tariff"] * (meter_insert["night"] - last_meters_data["night"]))
        meter_insert["cost"] = cost
        self.meters_data.insert_one(meter_insert)
        self.__general_data_update("last_meters_data", meter_insert)
        return cost, fake

    def add_meter(self, meter_id: int):
        if meter_id < 0:
            raise ValueError(f"Meter id can't be lower than 0. {meter_id} was given.")
        try:
            self.meters.insert_one({"meter_id": meter_id})
            return True
        except DuplicateKeyError:
            return False

    def add_tariff(self, day_tariff: float, night_tariff: float, set_as_current: bool = False):
        if day_tariff <= 0:
            raise DayTariffIsLowerThanZero(f"Day tariff can't be free. {day_tariff} price was given.")
        if night_tariff <= 0:
            raise NightTariffIsLowerThanZero(f"Night tariff can't be free. {night_tariff} price was given.")

        inserted_id = self.tariff_history.insert_one({
            "day_tariff": day_tariff,
            "night_tariff": night_tariff,
            "date_time": datetime.now()
        }).inserted_id

        if set_as_current:
            self.set_tariff(inserted_id)

        return inserted_id

    def set_tariff(self, tariff_id: str):
        try:
            id = ObjectId(tariff_id)
            found = self.tariff_history.find_one({"_id": id})
        except (TypeError, bson.errors.InvalidId):
            return False

        if not found:
            return False

        self.__general_data_update("current_tariff", found)
        return True

    def __general_data_update(self, _id: str, data: dict | Mapping):
        self.general_data.update_one(
            {"_id": _id},
            {"$set": {"data": data}},
            upsert=True
        )

    def __general_data_get(self, _id: str):
        result = self.general_data.find_one({"_id": _id})
        if not result:
            return result

        return result.get("data")
