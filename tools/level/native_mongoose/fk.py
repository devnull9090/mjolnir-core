import os
import json, sys, math
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import ce_vehicle_physics as P


def qm(a, b):
    ax, ay, az, aw = a
    bx, by, bz, bw = b
    return np.array([aw*bx+ax*bw+ay*bz-az*by, aw*by-ax*bz+ay*bw+az*bx, aw*bz+ax*by-ay*bx+az*bw, aw*bw-ax*bx-ay*by-az*bz])


def qr(q, v):
    u = np.array(q[:3]); v = np.array(v, float)
    c = np.cross(u, v)
    return v + 2*(q[3]*c + np.cross(u, c))


def conj(q):
    return np.array([-q[0], -q[1], -q[2], q[3]])


def skeleton(path='w_skeleton_model.json'):
    f = P.flatten(json.load(open(path))['fields'])
    n = P.count(f, 'nodes')
    out = []
    for i in range(n):
        p = f'nodes[{i}].'
        par = f[p+'parent node']
        out.append(dict(name=f[p+'name'], parent=-1 if par == 'none' else int(par.lstrip('#')),
                        t=np.array(P.vec(f[p+'default translation'])), q=np.array(P.vec(f[p+'default rotation'])),
                        inv=[P.vec(f[p+'inverse '+k]) for k in ('forward', 'left', 'up', 'position')], iscale=float(f[p+'inverse scale'])))
    for i, x in enumerate(out):
        if x['parent'] < 0:
            x['wq'], x['wt'] = x['q'], x['t']
        else:
            pa = out[x['parent']]
            x['wq'] = qm(pa['wq'], x['q'])
            x['wt'] = pa['wt'] + qr(pa['wq'], x['t'])
    return f, out


if __name__ == '__main__':
    f, s = skeleton()
    for i in (0, 1, 2, 4, 5, 30, 60, 104):
        x = s[i]
        M = np.array([qr(x['wq'], e) for e in np.eye(3)]).T  # columns: images of axes
        print(i, x['name'], 'wq', x['wq'].round(3), 'wt', x['wt'].round(3))
        print('   X->', M[:, 0].round(3), 'Y->', M[:, 1].round(3), 'Z->', M[:, 2].round(3))
        print('   inv', [np.round(v, 3).tolist() for v in x['inv']])
    for nm in ('wheel_front_left', 'wheel_hinge_front_left', 'wheel_hinge_front_right', 'steering_wheel', 'suspension_arm_back_left', 'suspension_arm_front_left', 'axle_base_front_left'):
        x = next(n for n in s if n['name'] == nm)
        print(nm, 'wt', x['wt'].round(3), 'X->', qr(x['wq'], [1, 0, 0]).round(3), 'Y->', qr(x['wq'], [0, 1, 0]).round(3), 'Z->', qr(x['wq'], [0, 0, 1]).round(3))
