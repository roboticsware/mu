import os
import gettext

from PyQt5.QtCore import QLocale

# DEBUG/TRANSLATE: override the language code here (e.g. to Chinese).
# language_code = 'zh'
language_code = QLocale.system().name()
if language_code == 'ru_RU':
    language_code = 'uz_UZ' # If RU, make default lang UZ

# Configure locale and language
# Define where the translation assets are to be found.
localedir = os.path.abspath(os.path.join(os.path.dirname(__file__), "locale"))
gettext.translation(
    "mu", localedir=localedir, languages=[language_code], fallback=True
).install()


def set_language(language_code, localedir=localedir):
    """
    Utility function to allow admin pane updates to change the locale.
    """
    gettext.translation(
        "mu", localedir=localedir, languages=[language_code], fallback=True
    ).install()
