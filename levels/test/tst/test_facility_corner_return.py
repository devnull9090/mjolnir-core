"""Checks for the small corner filling the indoor facility's end turns."""
import unittest

from facility_architecture import blind_end_corner_plan, CORNER_RETURN_Z


def in_triangle(point, triangle):
    def cross(a, b, p):
        return (b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0])
    values=[cross(a,b,point) for a,b in zip(triangle,triangle[1:]+triangle[:1])]
    return all(v >= -1e-8 for v in values) or all(v <= 1e-8 for v in values)


class CornerReturnTest(unittest.TestCase):
    def test_visible_slit_is_filled_on_all_four_turns(self):
        # These independent world-space probes lie in the formerly visible
        # gap, between the end of the sidewall and the blind cap.
        for side in (-1, 1):
            for rear in (False, True):
                with self.subTest(side=side, rear=rear):
                    poly=blind_end_corner_plan(side,rear)
                    for x,y in ((43.65,26.10),(43.75,26.20),(43.78,26.30)):
                        self.assertTrue(in_triangle((side*x,80.5-y if rear else y),poly))
                    # The 2 m turning bay ends at |x|=41; this detail stays
                    # beyond it and spans from the walking floor to the roof.
                    self.assertGreater(min(abs(x) for x,_ in poly),41.0)
                    self.assertEqual(CORNER_RETURN_Z,(0.30,4.015))

    def test_return_meets_each_solid_face(self):
        for side in (-1,1):
            for rear in (False,True):
                wall=54.5 if rear else 26.0
                poly=blind_end_corner_plan(side,rear)
                inward=-1 if rear else 1
                # Probes are strictly inside the old cap and adjoining wall,
                # proving overlap rather than merely coplanar contact.
                self.assertTrue(in_triangle((side*43.82,wall+inward*.20),poly))
                self.assertTrue(in_triangle((side*43.75,wall-inward*.12),poly))


if __name__ == '__main__':
    unittest.main()
