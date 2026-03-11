"""Constants for the GQ GMC-500 integration."""

DOMAIN = "gmc500"

DEFAULT_PORT = 8080
GMCMAP_URL = "https://www.gmcmap.com/log2.asp"
GMCMAP_TIMEOUT = 10
GMCMAP_MAX_RETRIES = 3

CONF_PORT = "port"
CONF_IGNORED_DEVICES = "ignored_devices"

# GMC-500 request parameter names
PARAM_AID = "AID"
PARAM_GID = "GID"
PARAM_CPM = "CPM"
PARAM_ACPM = "ACPM"
PARAM_USV = "uSV"
PARAM_TMP = "tmp"
PARAM_HMDT = "hmdt"
PARAM_AP = "ap"

REQUIRED_PARAMS = [PARAM_AID, PARAM_GID, PARAM_CPM, PARAM_ACPM, PARAM_USV]
OPTIONAL_PARAMS = [PARAM_TMP, PARAM_HMDT, PARAM_AP]

# Availability timeout: 3x default logging interval of 5 minutes
AVAILABILITY_TIMEOUT = 900  # 15 minutes in seconds
