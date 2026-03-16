# enums.py

from enum import Enum, auto


class SupplyCommand(Enum):
    # Basic control (common)
    OPEN_OUTPUT = auto()
    CLOSE_OUTPUT = auto()
    SET_VOLTAGE = auto()
    SET_CURRENT = auto()
    MEASURE_VOLTAGE = auto()
    MEASURE_CURRENT = auto()
    IDN = auto()
    RESET = auto()

    # Remote/local controls (common-ish)
    SYSTEM_REMOTE = auto()
    SYSTEM_LOCAL = auto()
    SYSTEM_RWLOCK = auto()

    # Range controls (E3645A-style)
    SET_RANGE_LOW = auto()
    SET_RANGE_HIGH = auto()

    # OVP controls (E3645A-style / SCPI)
    OVP_SET = auto()
    OVP_ENABLE = auto()
    OVP_DISABLE = auto()
    OVP_CLEAR = auto()

    # OCP controls (Over Current Protection)
    OCP_SET = auto()
    OCP_ENABLE = auto()
    OCP_DISABLE = auto()
    OCP_CLEAR = auto()

    # Multi-rail selection (E3631A-style)
    SELECT_P6V = auto()
    SELECT_P25V = auto()
    SELECT_N25V = auto()

    # Convenience command (some supplies support APPLY)
    APPLY = auto()

# Hata sorgusu (E3631A User's Guide, Sayfa 82)
      # SYST:ERR? hata kuyruğundaki son hatayı döner.
      # Hata yoksa "+0, No error" döner.
    SYSTEM_ERROR = auto()

 # Komut tamamlanma kontrolü (E3631A User's Guide, Sayfa 97)
    # *OPC? tüm bekleyen işlemler bittiyse 1 döner.
    OPC_QUERY = auto()
    
    # Test hook
    ECHO_TEST = auto()
