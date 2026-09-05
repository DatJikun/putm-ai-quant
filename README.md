# AeroPack

Warsztat do **recenzji CFD bolidu Formula Student** przez agenta AI.

Pytanie wyjściowe: mamy `.cas`/`.dat` z Fluenta, ~1500 zdjęć post-processingu (cały bolid + osie X/Y/Z) i oryginalny model CAD. Czy da się to skwantyfikować i wrzucić agentowi?

**Tak — ale jako pack, nie jako dump.** Ten repo pokazuje kontrakt danych, redukcję 1500 klatek do hero ramek i recenzenta aero na syntetycznym case FS-26.

**Handoff dla lokalnego agenta (źródło prawdy):** [BRIEFING.md](./BRIEFING.md)

Szablon kart geometrii (profil, cięciwa, AoA): [templates/geometry.yaml](./templates/geometry.yaml)

## Co tu jest

- Werdykt researchu i 12 źródeł (Navier Post-Processing Agent, AI CFD Scientist, CFDagent, AeroAgent, PyFluent FileSession, FluentCFFReader, Tampere FS, WAK Dynamic, …).
- Demo katalogu **dokładnie 1500** klatek z osiami, polami i regionami.
- Selector **hero** (ok. 15–20 PNG), które wolno pokazać VLM.
- KPI + CAD + jakość case (residuale, y+).
- JSON/prompt `aeropack/v1` i silnik oceny (reguły FS, nie czat).

Kontury w UI są znacznikami stacji, nie prawdziwym wynikiem Fluenta.

## Uruchomienie

```bash
npm install
npm run dev
```

Aplikacja: [http://127.0.0.1:43147](http://127.0.0.1:43147)

## Jak podłączyć prawdziwe dane

1. **Fluent** — trzymaj CFF (`.cas.h5` / `.dat.h5`). Offline: [PyFluent FileSession](https://fluent.docs.pyansys.com/version/stable/user_guide/offline/file_session.html) albo [FluentCFFReader](https://github.com/RezaNajian/FluentCFFReader). Z GUI zrzuc `report-definitions` (siły po ścianach), residuale, y+. Stary binarny `.cas` bez HDF5: eksport EnSight/VTK albo jeden przebieg headless.
2. **CAD** — STEP/STL: wheelbase, track, ride height, rake, Aref, lista części. To kotwica stacji (`X=0.70 m` = oś przednia).
3. **Zdjęcia** — nazwy `oś_stacja_pole.png` (albo sidecar JSON). 1500 plików zostaje na dysku; agent dostaje indeks + 15–30 hero.
4. **Agent** — multimodalny model z tool calling: najpierw pack, potem dopytanie o konkretną stację. Nie wklejaj całego volume mesh.

## Czego tu nie ma (celowo)

Licencji Ansys, parsera Twoich prywatnych `.dat`, prawdziwego VLM w chmurze. Demo ma pokazać kształt packa. Gdy wrzucisz folder z case’em, ten sam schemat się wypełnia.

## Stack

Next.js, TypeScript, Tailwind, shadcn/ui.
