class MeterIdNotFoundError(Exception):
    pass

class TariffIsNotSetError(Exception):
    pass

class NegativeValuesError(Exception):
    pass

class NightTariffIsLowerThanZero(Exception):
    pass

class DayTariffIsLowerThanZero(Exception):
    pass