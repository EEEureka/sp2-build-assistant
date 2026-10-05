import unittest
from review_restore_state import audit


def aircraft(rotation, position='0,0,0'):
    return f'<Aircraft><Assembly><Parts><Part id="1" rotation="{rotation}" position="{position}" /></Parts></Assembly></Aircraft>'


class RestoreDecimalBoundaryTests(unittest.TestCase):
    def test_exact_decimal_threshold(self):
        result = audit(aircraft('271.1128,112.1081,-0.0001758468'), aircraft('271.1128,112.1082,-0.0001758464'))
        self.assertTrue(result['equivalent'])
        self.assertEqual(result['normalizedEuler'][0]['maxEulerDeltaDegrees'], .0001)

    def test_threshold_not_relaxed(self):
        self.assertFalse(audit(aircraft('0,0,0'), aircraft('0.00010000001,0,0'))['equivalent'])

    def test_wrap_and_negative_angles(self):
        self.assertTrue(audit(aircraft('-0.00005,0,360'), aircraft('0.00005,360,0'))['equivalent'])
        self.assertFalse(audit(aircraft('359.99994,0,0'), aircraft('0.00005,0,0'))['equivalent'])

    def test_no_other_field_normalization(self):
        self.assertFalse(audit(aircraft('0,0,0'), aircraft('360,0,0', '0.000001,0,0'))['equivalent'])

    def test_nonfinite_rejected(self):
        for value in ('NaN','Infinity','-Infinity'):
            self.assertFalse(audit(aircraft('0,0,0'), aircraft(value+',0,0'))['equivalent'])


if __name__ == '__main__':
    unittest.main()
