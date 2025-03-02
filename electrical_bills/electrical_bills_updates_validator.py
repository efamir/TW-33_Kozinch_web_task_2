from pydantic import BaseModel, ValidationError
from typing import Union
from electricall_bills import ElectricalBills
from electricall_bills_exceptions import *


class AddMeterDataRequest(BaseModel):
    meter_id: int
    day: float
    night: float


class AddMeterRequest(BaseModel):
    meter_id: int


class AddTariffRequest(BaseModel):
    day_tariff: float
    night_tariff: float
    set_as_current: bool = False


class SetTariffRequest(BaseModel):
    tariff_id: str


class ActionRequest(BaseModel):
    data: Union[AddMeterDataRequest, AddMeterRequest, AddTariffRequest, SetTariffRequest]
    routing_key: str


def validate_and_execute_update(eb: ElectricalBills, message: dict) -> Exception | None:
    try:
        validated_request = ActionRequest(**message)
    except ValidationError as e:
        return e

    try:
        match validated_request.data:
            case AddMeterDataRequest(day=day, night=night, meter_id=meter_id):
                try:
                    cost, fake = eb.add_meter_data(meter_id=meter_id, day=day, night=night)
                    if fake:
                        raise Exception(
                            "Покази лічильника було накручено, "
                            "тому було автоматично встановленно споживання (див. таблицю)."
                        )
                except NegativeValuesError:
                    raise NegativeValuesError("Було отримано від'ємне число.")
                except MeterIdNotFoundError:
                    raise MeterIdNotFoundError(f"Лічільника з id {meter_id} не існує.")
                except TariffIsNotSetError:
                    raise TariffIsNotSetError("Не можна ввести показники поки не встановлено тариф.")
            case AddMeterRequest(meter_id=meter_id):
                if not eb.add_meter(meter_id=meter_id):
                    raise Exception(f"Айді лічільника {meter_id} вже існує. Спробуйте інший.")
            case AddTariffRequest(day_tariff=day_tariff, night_tariff=night_tariff, set_as_current=set_as_current):
                try:
                    eb.add_tariff(day_tariff=day_tariff, night_tariff=night_tariff, set_as_current=set_as_current)
                except Exception:
                    raise DayTariffIsLowerThanZero("Тариф не може бути безшкоштовним або мати від'ємне значення")
            case SetTariffRequest(tariff_id=tariff_id):
                if not eb.set_tariff(tariff_id=tariff_id):
                    raise Exception(f"Айді тарифу зі значенням {tariff_id} не існує. Спробуйте інший.")
    except Exception as e:
        return e
