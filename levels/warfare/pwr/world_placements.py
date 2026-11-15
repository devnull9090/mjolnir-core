"""Source scenario placements from the finalized manifest and prepared terrain."""
import math

def placements(layout,geometry,field):
    result={"sky":r"sky\clear afternoon\clear afternoon","scenery":[],"vehicles":[],
            "spawns":[],"flags":[],"pickups":[],"lights":[],"teleporters":[],"warfare":layout}
    tags={"warthog":r"vehicles\warthog\mp_warthog","scorpion":r"vehicles\scorpion\scorpion_mp",
          "banshee":r"vehicles\banshee\banshee_mp"}
    sites={s["id"]:s for s in geometry["sites"]}
    for team,name in enumerate(("red","blue")):
        home=layout["homes_m"][name];yaw=0 if team==0 else 180
        result["flags"].append({"team":team,"position_m":[*home[:2],home[2]+.65],"yaw_degrees":yaw})
        for point in layout["spawns_m"][name]:
            result["spawns"].append({"team":team,"position_m":point,"yaw_degrees":yaw,"modes":["ctf","slayer"]})
        centre=sites[name+"_home"]["position_m"]
        fleet=[("warthog",x,-42) for x in (-48,-32,32,48)]
        fleet += [("scorpion",x,-62) for x in (-40,40)]+[("banshee",x,-78) for x in (-25,25)]
        for kind,dx,dy in fleet:
            x,y=centre[0]+dx,centre[1]+dy
            # The radius78 twelve-sided podium's apothem bounds this apron.
            floor=max(float(field.sample(x,y)),centre[2]+.35 if math.hypot(dx,dy)<75 else -1e6)
            result["vehicles"].append({"tag":tags[kind],"team":team,
                "position_m":[x,y,floor+(2 if kind=="banshee" else 1)],"yaw_degrees":yaw})
        for tag,dx,dy in [(r"item collections\single weapons\assault rifle",-12,4),
                          (r"item collections\single weapons\pistol",12,4),
                          (r"item collections\powerups\powerup health pack",0,-10)]:
            result["pickups"].append({"tag":tag,"position_m":[home[0]+dx,home[1]+dy,home[2]+.6],"yaw_degrees":yaw})
    return result
