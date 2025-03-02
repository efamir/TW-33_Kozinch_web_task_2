import unittest
from mongomock import MongoClient

from electricall_bills import ElectricalBills
from electricall_bills_exceptions import *


class TestElectricalBills(unittest.TestCase):
    def setUp(self):
        self.client = MongoClient()
        self.db = self.client["test_db"]
        self.eb = ElectricalBills(self.db)

    # Тести додавання показів
    def test_add_meter_data_meter_id_not_found(self):
        """Спроба додати дані для неіснуючого лічильника"""
        with self.assertRaises(MeterIdNotFoundError):
            self.eb.add_meter_data(1, 10.0, 5.0)

    def test_add_meter_data_no_tariff_set(self):
        """Помилка при відсутності тарифу"""
        self.eb.add_meter(1)
        with self.assertRaises(TariffIsNotSetError):
            self.eb.add_meter_data(1, 10.0, 5.0)

    def test_add_meter_data_first_insertion(self):
        """Перший запис показів"""
        self.eb.add_meter(1)
        self.eb.add_tariff(1.0, 0.5, set_as_current=True)
        cost, _ = self.eb.add_meter_data(1, 10.0, 5.0)

        self.assertEqual(cost, 12.5)
        self.assertEqual(self.eb.meters_data.count_documents({}), 1)

        last_data = self.db["general_data"].find_one({"_id": "last_meters_data"})["data"]
        self.assertEqual(last_data["meter_id"], 1)
        self.assertEqual(last_data["day"], 10.0)

    def test_add_meter_data_subsequent_greater_values(self):
        """Додавання нових показів більших за попередні"""
        self.eb.add_meter(1)
        self.eb.add_tariff(1.0, 0.5, set_as_current=True)
        self.eb.add_meter_data(1, 10.0, 5.0)

        cost, _ = self.eb.add_meter_data(1, 15.0, 7.0)
        self.assertEqual(cost, 6.0)
        self.assertEqual(self.eb.meters_data.count_documents({}), 2)

    def test_add_meter_data_with_adjustment_day(self):
        """Корекція денних показів"""
        self.eb.add_meter(1)
        self.eb.add_tariff(1.0, 0.5, set_as_current=True)
        self.eb.add_meter_data(1, 10.0, 5.0)
        cost, _ = self.eb.add_meter_data(1, 9.0, 6.0)
        self.assertEqual(cost, 1.0 * 100 + 0.5 * (6.0 - 5.0))
        data = self.eb.meters_data.find_one({"meter_id": 1, "day": 110.0, "night": 6.0})
        self.assertIsNotNone(data)

    def test_add_meter_data_with_adjustment_night(self):
        """Корекція нічних показів"""
        self.eb.add_meter(1)
        self.eb.add_tariff(1.0, 0.5, set_as_current=True)
        self.eb.add_meter_data(1, 10.0, 5.0)
        cost, _ = self.eb.add_meter_data(1, 11.0, 4.0)
        self.assertEqual(cost, 1.0 * (11.0 - 10.0) + 0.5 * 80)
        data = self.eb.meters_data.find_one({"meter_id": 1, "day": 11.0, "night": 85.0})
        self.assertIsNotNone(data)

    def test_add_meter_data_with_adjustment_day_and_night(self):
        """Корекція нічних та денних показів"""
        self.eb.add_meter(1)
        self.eb.add_tariff(1, 1, set_as_current=True)
        self.eb.add_meter_data(1, 10.0, 5.0)
        cost, _ = self.eb.add_meter_data(1, 9.0, 4.0)
        self.assertEqual(cost, 1.0 * 100 + 1 * 80)
        data = self.eb.meters_data.find_one({"meter_id": 1, "day": 110.0, "night": 85.0})
        self.assertIsNotNone(data)

    def test_add_meter_data_multiple_meters(self):
        """Робота з кількома лічильниками"""
        self.eb.add_meter(1)
        self.eb.add_meter(2)
        self.eb.add_tariff(1.0, 0.5, set_as_current=True)

        self.eb.add_meter_data(1, 10.0, 5.0)
        cost, _ = self.eb.add_meter_data(2, 20.0, 10.0)
        self.assertEqual(cost, 12.5)

    # Тести додавання лічильників
    def test_add_meter_negative_id(self):
        """Спроба додати лічильник з від'ємним ID"""
        with self.assertRaises(ValueError):
            self.eb.add_meter(-1)

    def test_add_meter_success(self):
        """Успішне додавання лічильника"""
        self.eb.add_meter(1)
        self.assertEqual(self.eb.meters.count_documents({}), 1)
        self.assertIsNotNone(self.eb.meters.find_one({"meter_id": 1}))

    def test_add_meter_duplicate(self):
        """Спроба додати дубльований ID"""
        self.eb.add_meter(1)
        result = self.eb.add_meter(1)
        self.assertFalse(result)

    # Тести для тарифів
    def test_add_tariff_day_tariff_zero(self):
        """Нульовий денний тариф"""
        with self.assertRaises(DayTariffIsLowerThanZero):
            self.eb.add_tariff(0.0, 1.0)

    def test_add_tariff_night_tariff_negative(self):
        """Від'ємний нічний тариф"""
        with self.assertRaises(NightTariffIsLowerThanZero):
            self.eb.add_tariff(1.0, -1.0)

    def test_add_tariff_set_as_current(self):
        """Встановлення нового тарифу"""
        tariff_id = self.eb.add_tariff(1.0, 0.5, set_as_current=True)
        current_tariff = self.db["general_data"].find_one({"_id": "current_tariff"})["data"]
        self.assertEqual(str(current_tariff["_id"]), str(tariff_id))

    def test_set_tariff_non_existent(self):
        """Спроба використати неіснуючий тариф"""
        self.assertFalse(self.eb.set_tariff("fake_id"))

    def test_set_tariff_existing(self):
        """Переключення існуючого тарифу"""
        tariff_id = self.eb.add_tariff(1.0, 0.5)
        self.eb.set_tariff(str(tariff_id))

        current_tariff = self.db["general_data"].find_one({"_id": "current_tariff"})["data"]
        self.assertEqual(str(current_tariff["_id"]), str(tariff_id))


if __name__ == '__main__':
    unittest.main()
