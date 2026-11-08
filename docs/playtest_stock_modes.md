# Two-PC test: stock game types

For the test kit `mjolnir-stock-modes-20261105`, built from
`work/megalo-script-traits`. It covers what one PC cannot prove: bots are not
players to the scripts, so they never hold a hill, contest it or become "it".
About an hour. Work down the list: the first three sections matter most.

## Setup, on both PCs

1. Update the MJOLNIR launcher and mods, then close the game and the launcher.
2. Make sure Blood Gulch and Prisoner are installed.
3. Run the kit's installer:

   ```powershell
   powershell -ExecutionPolicy Bypass -File install_stock_modes.ps1
   ```

4. Run it again with `-Check`. Both PCs must print the same lines.
5. Start the game from Steam, not the launcher.

Set **BOTS to 0** in Game Settings: it keeps the score clean. A public game
appears in hub history, so join by invite if you can.

If something fails, note the section and copy
`Meteorite\Binaries\Win64\ue4ss\UE4SS.log` from both PCs before closing the game.

## 1. Team King (Blood Gulch)

Host: GAME TYPE, KING OF THE HILL, TEAM KING, SELECT. On a UI pack from before the
variant buttons, click KING OF THE HILL until it says Team King. Juggernaut,
Stalker and Reverse Tag are then under ODDBALL, and Rally under RACE.

- [ ] The players land on opposite teams, and the bar reads RED and BLUE on both PCs.
- [ ] The wall and beacon stand on the same hill on both PCs.
- [ ] One player on the hill: the wall turns their team's colour on both PCs. Their team gains 1 a second.
- [ ] Both on the hill: flashing violet, HILL CONTESTED, and nobody scores.
- [ ] One leaves: scoring starts again for the other.
- [ ] After 60 s the hill moves to the same place on both PCs.
- [ ] The score bar matches on both PCs.

## 2. Juggernaut (Blood Gulch)

- [ ] Nobody is the Juggernaut at the start.
- [ ] The first kill makes the killer the Juggernaut: +1, a beacon over their head for the others, YOU ARE THE JUGGERNAUT and no beacon for them.
- [ ] The other player sees the beacon follow them smoothly, into a vehicle too.
- [ ] Killing the Juggernaut passes it on, with +1 and the beacon moving.
- [ ] Each Juggernaut kill scores +1.
- [ ] A Juggernaut who falls or suicides frees the slot, and the beacon goes.
- [ ] The Juggernaut kills in fewer shots than the other player, and melee hits harder.
- [ ] First to 15 ends the match, and the post-game screen agrees on both PCs.

## 3. Race (Prisoner)

On foot. Set RACE on the Race tile.

- [ ] Each PC shows its own next flag, and they differ once one player gets ahead.
- [ ] The line counts up: FLAG 2 OF 9 and so on.
- [ ] Touching the last flag and then the first scores a lap, and LAP 2 OF 3 shows.
- [ ] Dying and respawning keeps your place.
- [ ] Three laps ends the match.

## 4. Stalker (Blood Gulch)

- [ ] The first kill makes the killer the Stalker: invisible, faster, and YOU ARE THE STALKER for them only.
- [ ] Nobody sees a beacon on the Stalker.
- [ ] The hunter takes about twice the shots to die as in Slayer.
- [ ] Is it playable with no marker on the Stalker? CE's hunters had a motion tracker blip.

## 5. Reverse Tag (Blood Gulch)

- [ ] Nobody scores until the first kill.
- [ ] "It" scores 1 a second, sees YOU ARE IT, and moves slower.
- [ ] Killing "it" passes it on, and the beacon moves.

## 6. King and Crazy King (Prisoner)

- [ ] King: the hill never moves. One player scores 1 a second.
- [ ] Two players on it: violet, HILL CONTESTED, no score.
- [ ] Crazy King: the hill moves every 60 s, never to the same hill twice running.

## 7. Team Oddball and Oddball (Prisoner)

- [ ] Team Oddball: the carrier scores 1 a second for their team.
- [ ] The bar matches on both PCs.
- [ ] Oddball: first to 120 ends the match.
- [ ] A skull marker shows the ball on every PC: gold while it lies, orange while carried, none for the carrier.

## 8. Rally and Team Race (Prisoner, then Blood Gulch)

- [ ] Rally: the same flag shows on both PCs.
- [ ] Touching it scores, and it moves on both PCs.
- [ ] Team Race on Blood Gulch: touching a flag in a Warthog counts, for driver and passenger.

## 9. Slayer, CTF and joining late

- [ ] Slayer: a suicide takes a point. The board and the hub report stay sane at -1.
- [ ] CTF: a capture still scores.
- [ ] Start Crazy King and join from PC 2 a minute in: PC 2 runs the same mode, and shows the right hill by its first spawn.
- [ ] Start Juggernaut and join late: PC 2 sees the beacon by its first spawn.

## Undo, on both PCs

```powershell
powershell -ExecutionPolicy Bypass -File install_stock_modes.ps1 -Restore
```
