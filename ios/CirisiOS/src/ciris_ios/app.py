import toga
from toga.style import Pack
from toga.style.pack import COLUMN
import sys

# Import CIRIS dependencies to verify they load
try:
    import pydantic
    from pydantic_core import _pydantic_core
    PYDANTIC_STATUS = f"Pydantic: {pydantic.VERSION} (Core: {_pydantic_core.__version__})"
except ImportError as e:
    PYDANTIC_STATUS = f"Pydantic Error: {e}"

try:
    import cryptography
    CRYPTO_STATUS = f"Cryptography: {cryptography.__version__}"
except ImportError as e:
    CRYPTO_STATUS = f"Crypto Error: {e}"

class CirisiOS(toga.App):
    def startup(self):
        main_box = toga.Box(style=Pack(direction=COLUMN))

        main_box.add(toga.Label("CIRIS iOS Runtime", style=Pack(padding=10)))
        main_box.add(toga.Label(PYDANTIC_STATUS, style=Pack(padding=10)))
        main_box.add(toga.Label(CRYPTO_STATUS, style=Pack(padding=10)))

        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = main_box
        self.main_window.show()

def main():
    return CirisiOS()
