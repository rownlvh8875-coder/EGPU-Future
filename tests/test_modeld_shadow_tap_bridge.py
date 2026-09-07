from integrations.openpilot.modeld_shadow_tap_bridge import ModeldShadowTapBridge


class OfficialModel:
  chestnut = True


class OfficialSmall:
  chestnut = False


class CarrotBig:
  usbgpu = True


class CarrotSmall:
  usbgpu = False


def test_backend_detection_supports_official_and_carrot():
  assert ModeldShadowTapBridge._is_big_model(OfficialModel())
  assert not ModeldShadowTapBridge._is_big_model(OfficialSmall())
  assert ModeldShadowTapBridge._is_big_model(CarrotBig())
  assert not ModeldShadowTapBridge._is_big_model(CarrotSmall())
