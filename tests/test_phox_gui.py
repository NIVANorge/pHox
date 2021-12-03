import asyncio
from unittest.mock import patch

from asyncqt import QEventLoop
from pytestqt.qt_compat import qt_api

from pHox_gui import boxUI


class Namespace:
    """Class for faking return value of argparse.ArgumentParser()).parse_args()"""

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_basics(qtbot):
    """
    Basic test that works more like a sanity check to ensure we are setting up a QApplication
    properly and are able to display a simple event_recorder.
    """
    assert qt_api.QApplication.instance() is not None

    loop = QEventLoop(qt_api.QApplication.instance())
    asyncio.set_event_loop(loop)
    faked_args = Namespace(co3=False, debug=True, pco2=False, seabreeze=False, stability=False)

    with patch("pHox_gui.argparse", autospec=True) as argparse_path, patch("pHox_gui.loop", loop) as patched_loop:
        argparse_path.ArgumentParser.return_value.parse_args.return_value = faked_args
        widget = boxUI()
        qtbot.addWidget(widget)

        assert widget.isVisible()
        assert widget.windowTitle() == "W1"
        assert 0
