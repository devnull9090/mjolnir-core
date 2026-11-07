# Play test: Yoyorast Island V2

For Yoyorast Island V2 2.7.0 with mods 0.46.0. Every game type below hosts and
runs on one PC, with its objectives and vehicles in the simulation. This list is
what one PC cannot prove: bots are not players to the scripts, so they never
score an objective, take a flag or become "it".

Two players is the minimum, one on each team. Four is better: a contested hill,
a betrayal and a shared team score all need more than one on a side. Work down
the list: the first three sections matter most.

## Setup, on every PC

1. Update the launcher and mods, and install Yoyorast Island 2.7.0.
2. Set **BOTS to 0** in Game Settings: it keeps the score clean.
3. Host privately if you can: a public game appears in hub history.

If something fails, note the section and copy
`Meteorite\Binaries\Win64\ue4ss\UE4SS.log` from every PC before closing the game.

## 1. Joining

Host Slayer, then have everyone join.

- [ ] Everyone loads into the match and sees the same score.
- [ ] Two Mongooses stand at the top of the ramp, and every player sees them.
- [ ] A joiner hears a vehicle's engine, and sees it move.

## 2. The Mongoose

- [ ] Drive it off a high ledge onto the beach. It lands on its wheels and drives
      away. It used to sink into the ground for good.
- [ ] Brake hard, watching from behind. The lamps glow, not just the ground.
- [ ] A second player rides on the back, and both see the same thing.

## 3. Assault (new)

Assault is new and has never been played by two people. It is under Capture the
Flag. Blue defends first.

- [ ] One flag is out, on Blue's stand. Red can take it, and Blue cannot.
- [ ] Red carries it to Red's own stand: Red scores, and the flag appears on
      Red's stand with Blue attacking.
- [ ] Nobody captures for five minutes: the flag goes home and the sides swap.
- [ ] A dropped flag goes home after 30 seconds, or when a defender touches it.
- [ ] Three captures end the game, and the score screen is right.
- [ ] The flag's colour and the HUD agree with who is defending.
- [ ] A marker shows the flag and how far it is. It stays on the flag when someone
      carries it, on every player's screen, and moves when the sides swap.
- [ ] The line under the score says ATTACK or DEFEND, correctly for each player, and
      counts down to the swap. Someone who joins late sees the countdown after the
      first swap, not before.

## 4. Capture the Flag

- [ ] Take the enemy flag to your stand: your team scores, and only while your own
      flag is home.
- [ ] A carrier dies: the flag drops, and its own team returns it by touching it.
- [ ] Every Warthog and Mongoose is on the map, in this game type too. They used to
      go missing here.

## 5. Team Slayer

- [ ] A kill scores for the team, on every player's HUD.
- [ ] With three or more players, killing a teammate costs a point.

## 6. King of the Hill

- [ ] **King:** standing alone on the hill scores. A second player on it stops the
      scoring, and the hill's colour shows it.
- [ ] **Crazy King:** the hill moves every minute, to somewhere you can reach.
- [ ] **Team King:** teammates on the hill do not contest each other.

## 7. Oddball, Juggernaut

- [ ] **Oddball:** the carrier scores a point a second. Killing them drops the
      ball, and it returns if left alone.
- [ ] **Team Oddball:** the carrier's points go to their team.
- [ ] **Juggernaut:** the first kill makes you it, and killing it passes it on.
- [ ] **Stalker:** the Stalker is invisible and fast, and takes the role by killing.
- [ ] **Reverse Tag:** whoever is it runs slower and scores a point a second.

## 8. Race

Yoyorast's lap is 27 flags and about 2.2 km. Nobody has finished one yet, so the
first thing to find out is whether every flag can be reached.

- [ ] **Race:** drive a full lap in a Warthog or Mongoose. Each flag you touch moves
      the marker on, and a lap scores. Note any flag you can't reach.
- [ ] **Team Race:** each player's laps add to the team's.
- [ ] **Rally:** touching the live flag scores, and it moves somewhere else.
- [ ] **Team Rally:** those points go to the team.

The Scorpion and Banshee are on the map in Race. In CE's Race they were not.

## 9. Gates, shields and teleporters

- [ ] A button raises its gate for a client as well as the host.
- [ ] A gate blocks a player and a vehicle while it is up.
- [ ] A panic shield comes up, blocks, and drops after a minute.
- [ ] The teleporters work in both directions.

## 10. Forge

- [ ] Host FORGE. The map's vehicles are there, including the two on the ramp.
- [ ] A joiner sees them too. This has not been tried.
- [ ] Grab one with the Monitor, move it, press F5, then host Slayer. It starts at
      its new spot.
