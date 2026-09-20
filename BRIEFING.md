# AeroPack — briefing dla lokalnego agenta

Ten plik jest źródłem prawdy. Przekaż go agentowi na komputerze, gdzie leżą pliki Fluent, CAD i zdjęcia. Nie zgaduj setupu — poniżej jest to, co ustaliliśmy.

Demo UI w chmurze (Next.js, syntetyczny FS-26) pokazuje kształt packa. **Lokalnie budujemy ingest + pack JSON + recenzenta**, nie kolejny slideshow.

---

## 0. Co budujemy (jedno zdanie)

Skrypt (Python), który z folderu case’a Fluent **zczytuje setup, siatkę, metody, residuale, siły, transcript, CAD/geometrię płatów i indeks zdjęć**, składa to w `aeropack.json` (+ wybrane PNG) i dopiero ten pack idzie do agenta AI recenzującego aero **połowy bolidu Formula Student, jazda na wprost**.

Nie wrzucamy agentowi surowych `.cas`/`.dat` ani 1500 PNG.

---

## 1. Pytanie wyjściowe i werdykt

**Pytanie:** wyniki Fluent (`.cas` + `.dat`), ~1500 zdjęć post-processingu (cały bolid + osie X/Y/Z), oryginalny model auta — czy da się to skwantyfikować i dać agentowi do oceny?

**Werdykt:** tak, jako **pack**, nie jako dump. Nikt nie opublikował gotowego klonu „Fluent FS + 1500 klatek + CAD → recenzent”. Kawałki istnieją (Navier, AI CFD Scientist, PyFluent FileSession, FluentCFFReader, Tampere FS). My składamy warstwę pod ten konkretny workflow.

---

## 2. Decyzje (1–4) — zaktualizowane

| # | Propozycja | Decyzja właściciela | Jak to realizujemy |
|---|------------|---------------------|-------------------|
| 1 | Liczby z solvera, nie z pikseli | **Tak, plus meshing i wszystkie metody.** Ma to zczytywać **skrypt**. Ansys zostawia też **transcripty**. | Parser: `.cas`/`.dat` (najlepiej CFF `.h5`) + `.trn` + `.jou` + raporty sił/y+/residuali + metadata siatki (typ komórek, pryzmy, jakość). |
| 2 | CAD jako linijka (wheelbase, RH) | **CAD jako wiele linijek.** Geometria ma być opisana: profil, cięciwa, gdzie się zaczyna/kończy, AoA, itd. | `geometry.yaml` (źródło prawdy zespołu) + opcjonalnie bbox z nazwanych brył STEP. Agent dostaje karty urządzeń aero, nie sam STL. |
| 3 | 1500 → 15–30 hero klatek | **Niepewne — „może tak”.** | Zawsze pełny **indeks** 1500. Domyślny zestaw hero ~25–40, konfigurowalny. Agent **dopytuje** o stację, zamiast dostać wszystko na start. Nie tniemy agresywnie. |
| 4 | Agent z tool calling | **Chyba tak.** | Tak. Pierwszy strzał: pack + hero. Tool: `get_frame(axis, station, field)`, `get_component_forces(name)`, `get_transcript_excerpt(keyword)`. |

**Setup fizyczny (doprecyzowanie):**

- siatka = **połowa bolidu** (płaszczyzna symetrii),
- warunek = **jazda na wprost** (yaw 0°),
- to nie jest full-car ani mapa yaw.

---

## 3. Czego agentowi nie wolno

- Odczytywać dokładnego Cl/Cd z PNG (colormap ≠ metrologia).
- Wnioskować stallu z jednej klatki — składa X (ślad) + Z (podłoga) + siłę komponentu.
- Łykać 18 mln komórek z `.dat` do kontekstu.
- Traktować yaw 0° / half-model jako pełny slalom FS. Pack sezonu to później V∞ × yaw × ride height; **teraz jeden typ case’a**.
- Mnożyć siły ×2 albo nie mnożyć **w ciemno**. Musi być jawne: `forceConvention: half | full-equivalent` i skąd Aref.

---

## 4. Folder wejściowy (to, czego szukać u właściciela)

Typowy dump Ansys/Fluent. Nie wszystkie pliki muszą być; skrypt ma **inwentaryzować co jest** i flagować braki.

```
case/
  *.cas  / *.cas.h5  / *.cas.gz      # setup + siatka
  *.dat  / *.dat.h5  / *.dat.gz      # rozwiązanie
  *.msh  / *.msh.h5                  # czasem osobno
  fluent-YYYYMMDD-HHMMSS-.trn        # transcript (konsola: input+output)
  *.jou                              # journal (same komendy TUI/Scheme)
  *.pzmcontrol                       # scoped prisms (jeśli meshing workflow)
  report*.out / *forces*.txt / *.csv # report-definitions, monitory
  residuals*.out
  *.cse                              # CFD-Post session (batch zdjęć)
  pictures/                          # ~1500 PNG
  cad/
    *.step / *.stp / *.stl
    geometry.yaml                    # KARTZ GEO — patrz §6 (to my tworzymy, jeśli nie ma)
```

**Transcript vs journal (ważne):**

| plik | co to jest | czy da się wczytać z powrotem do Fluenta |
|------|------------|------------------------------------------|
| `.jou` | komendy (TUI + Scheme z GUI) | tak — to skrypt |
| `.trn` | **cała konsola**: komendy + printy (mesh quality, residuale, wall-clock, force reports) | **nie** — tylko do parsowania |

Auto-transcript: `fluent-YYYYMMDD-HHMMSS-.trn` (Preferences → General → Automatic Transcript).

---

## 5. Warstwa 1 — skrypt zczytujący Fluent + siatkę + metody

Cel: `ingest/fluent_case.py` → sekcja `solver`, `mesh`, `methods`, `monitors` w packu.

### 5.1 Priorytet źródeł (od najlepszego)

1. **CFF** `.cas.h5` / `.dat.h5`
   - PyFluent `FileSession` / `CaseFile` / `DataFile` (bez GUI, nadal ekosystem Ansys)
   - albo `cffview --save case.json` / FluentCFFReader → VTP/VTU
2. **Transcript `.trn`** — regex na to, czego nie ma w czytelnym JSON-ie: jakość siatki, printy `/mesh/quality`, residuale iteracji, force report z konsoli, wersja Fluenta, liczba procesorów, czas sesji
3. **Journal `.jou`** — metody: modele, BC, schematy dyskretyzacji, ile iteracji, initialize
4. **CSV/OUT z Report Definitions** — siły po ścianach (to jest KPI, nie transcript)
5. Stary binarny `.cas`/`.dat` bez HDF5 — **nie parsować na siłę**. Albo jeden przebieg headless (`fluent 3d -g -i extract.jou`), albo eksport EnSight/VTK z GUI. Zanotuj w packu `casFormat: legacy-binary`.

### 5.2 Co konkretnie wyciągnąć

**Identyfikacja**

- Fluent version, 2d/3d, double precision, parallel N
- nazwa case, ścieżki cas/dat
- steady / transient
- pressure-based / density-based, coupled / SIMPLE / PISO

**Domena i BC (half-car, straight)**

- symmetry zone name
- velocity inlet / pressure outlet / ground (moving wall? rolling road?)
- wheel rotation (MRF / moving wall / sliding mesh) — **musi być w packu**, drag kół od tego żyje
- yaw = 0, V∞, ρ, μ, T
- reference values: `Aref`, `Lref`, `Vref` — **i czy Aref jest full frontal czy half**

**Modele**

- turbulencja (np. k-ω SST) + wall treatment (y+≈1 vs wall functions) + roughness jeśli jest
- energy on/off
- compressibility (zazwyczaj incompressible)
- gravity
- operating pressure

**Siatka / meshing**

To jest punkt 1 od właściciela — nie pomijać.

- liczba komórek, faces, nodes
- typy: poly / hexcore / poly-hexcore / tet / prisms
- warstwy przyścienne: first height, n layers, growth rate, last-ratio, scoped zones (wings vs floor vs wheels) — z `.pzmcontrol` albo transcript/journal
- BOI / body of influence (jeśli w journalu)
- jakość z `/mesh/quality` albo transcript:
  - min orthogonal quality (alarm < 0.01)
  - max aspect ratio
  - skewness jeśli jest
- y+ min/avg/max **per grupa ścian**: skrzydła, podłoga, koła, body (z data file albo raportu)

**Numeryka**

- spatial discretization (2nd order, bounded, …)
- pseudo-transient / coupled explicit/implicit
- URFs jeśli SIMPLE
- kryterium zbieżności, liczba iteracji faktycznie zrobionych
- residuale końcowe: continuity, xyz-mom, k, omega (albo epsilon)
- czy było averaging sił

**Siły (KPI)**

- Cl, Cd, Cs, Cm (oś — podać punkt momentu, zwykle środek rozstawu)
- po komponentach: FW, floor+diffuser, RW, wheels, body+hoop+driver
- `forceConvention`: `half` albo `full-equivalent` + `symmetryFactor: 2` jeśli pomnożone
- L/D, front aero balance %
- downforce/drag w Newtonach przy danym V∞

**Spójność metod vs wyniki (recenzent tego używa)**

- jeśli setup mówi y+≈1, a y+ avg na płatach = 40 → **issue**
- jeśli continuity > 1e-4 → nie porównuj geometrii na 3. miejscu po przecinku
- jeśli Aref half vs full pomieszane → **blocker**

### 5.3 Szkic parsera transcriptu

Szukaj m.in. (regex, nie pełny parser TUI):

```
Fluent .* Release
Orthogonal Quality
Maximum Aspect Ratio
Mesh contains .* cells
k-omega / SST / Spalart / Realizable
velocity-inlet / symmetry / moving wall
iter  continuity  x-velocity
Force  (n)  Drag  Lift
Wall-clock time
```

Zrzuc surowe trafienia do `transcriptHits[]` (linia + kontekst), a wartości liczbowe do pól schema. Nie wyrzucaj oryginalnego cytatu — agent ma evidence.

---

## 6. Warstwa 2 — geometria jako wiele linijek

STL/STEP sam z siebie **nie powie** „to S1223, cięciwa 220 mm, AoA 8°”. Nazwa profilu i kąt to **intencja projektowa**. Dlatego:

1. **Obowiązkowy** `geometry.yaml` (lub JSON) utrzymywany przez aero — źródło prawdy.
2. Opcjonalnie skrypt liczy z CAD bbox/named bodies: Xmin/Xmax, Zmin (ride height), span do symmetry.
3. Pack łączy: intencja (yaml) + zmierzone (CAD) + flagę jeśli się rozjeżdżają > tolerancji (np. 5 mm / 0.5°).

Układ współrzędnych (ustalić raz i wpisać w pack; typowy FS/Fluent):

- **X** — wzdłuż auta, nos → tył (albo odwrotnie — **zapisać znak**)
- **Y** — na zewnątrz od symmetry (`Y=0` = płaszczyzna cięcia, Y>0 = prawa połowa)
- **Z** — góra
- długości w **mm** w yaml, w metrach w polach Fluent

### 6.1 Globalny pojazd

```yaml
vehicle:
  name: FS-?? 
  halfModel: true
  yawDeg: 0
  rideHeightFrontMm: 25
  rideHeightRearMm: 32
  rakeDeg: 0.25
  wheelbaseMm: 1600
  trackMm: 1200          # full track; na half-modelu half-track = track/2
  frontalAreaM2: 0.92    # UWAGA: full albo half? pole: frontalAreaBasis: full
  origin: "symmetry plane, ground, X=0 at front axle"  # przykład — wpisać WASZ
```

### 6.2 Karta elementu nośnego (powtórzyć dla każdego płata)

To jest „wiele linijek”. Jedna karta = jeden płat / klapa / endplate / dyfuzor.

```yaml
devices:
  - id: fw-main
    group: front-wing
    role: mainplane
    profile: S1223          # albo E423 / MSHD / custom + ścieżka do .dat profilu
    profileSource: "airfoils/S1223.dat"
    chordMm: 280
    spanMm: 595             # od symmetry do endplate (half)
    incidenceDeg: 4.5       # AoA geometryczne względem X (podłoga / chassis)
    twistDeg: 0
    le:
      xMm: 120
      zMm: 45
    te:
      xMm: 400
      zMm: 38
    slotGapMm: null
    overlapMm: null
    gurneyMm: 0
    notes: "main FW, bez Gurneya"
```

Wymagane karty (minimum, nawet jeśli część TBD):

- front wing: main + każda klapa + endplate + footplate/cape jeśli jest
- rear wing: main + klapy + endplate (+ DRS closed, skoro jazda na wprost)
- floor / undertray: leading edge X, throat, kick-up start
- diffuser: kąt, długość, wysokość wylotu, liczba kanałów / fences
- sidepod inlet: X, Y, Z, area
- nose, hoop (wysokość — brudne powietrze na RW)
- koła: średnica, szerokość, camber jeśli w CAD

Dla klap dodać względem poprzedniego elementu: `overlapMm`, `slotGapMm`, `incidenceDeg`.

### 6.3 Po co to agentowi

Żeby zdanie „ssanie pada na 40% cięciwy górnego płata RW” miało kotwicę: `rw-flap2`, chord 180 mm, LE X=…, incidence 28°. Bez tego VLM opisuje tapetę.

---

## 7. Warstwa 3 — zdjęcia (~1500)

Konwencja nazw (wymusić albo sidecar JSON obok PNG):

```
{axis}_{stationMm}_{field}_{camera}.png
np. x_0700_cpt_yz.png
    y_0000_vel_symmetry.png
    z_0120_cpt_xy.png
    full_iso-rear_vel.png
```

**Half-model:**

- oś Y: stacje tylko `Y ≥ 0` (albo tylko symmetry `Y=0` + kilka offsetów do endplate)
- widoki „cały bolid” = half, ewentualnie mirrored w post — **zanotować czy mirror włączony**
- nie interpretować Cs≠0 jako yaw; to numeryka / niesymetria siatki

**Indeks zawsze pełny.** Hero na start (domyślnie, edytowalne):

- full: Cp iso-front, Cp bottom, |V| iso-rear, y+ top
- Y=0: Cp total + |V|
- Z podłoga (~RH) Cp total; Z wysokość płatów |V|
- X: FW, oś przednia, wlot podłogi, kokpit/hoop, oś tylna, dyfuzor, RW, near wake — pole **Cp total** + vorticity na osi przedniej

To jest punkt 3 „może tak”: hero jest **sugestią**, indeks jest obowiązkiem. Jeśli nazwy plików nie kodują stacji — najpierw naprawić nazwy / sidecar, nie wrzucać 1500 do VLM.

---

## 8. Warstwa 4 — agent

Nie jeden prompt z załącznikami.

**System:** recenzent aero FS, half-car, yaw 0. Liczby > piksele. Cytuj evidence (stacja, y+, residual, karta geometrii).

**Pierwszy strzał:** `aeropack.json` + hero PNG.

**Narzędzia:**

- `get_frame(axis, station_m, field)` → 1 PNG z indeksu
- `get_component_force(id)`
- `search_transcript(regex) → linie`
- `get_device(id)` → karta geometrii

**Werdykt:** `akceptowalne | warunkowo | do-poprawy | nieufne`  
plus: zbieżność, siatka/y+/metody, L/D, balans, pokrycie klatek, pytania do inżyniera, kolejne runy.

Porównuj do zakresów **FS**, nie F1. Na yaw 0 i half nie oceniaj zachowania w zakręcie.

---

## 9. Schema packa `aeropack/v1` (kontrakt)

```json
{
  "schema": "aeropack/v1",
  "generatedAt": "ISO-8601",
  "warnings": ["lista braków ingestu"],
  "identity": {
    "caseId": "",
    "vehicle": "",
    "halfModel": true,
    "yawDeg": 0,
    "speedMs": 15
  },
  "files": {
    "cas": "", "dat": "", "transcripts": [], "journals": [],
    "picturesDir": "", "cad": "", "geometryYaml": ""
  },
  "methods": { },
  "mesh": { },
  "monitors": { "residuals": {}, "yPlus": {}, "iterations": 0 },
  "kpis": { "forceConvention": "half|full-equivalent", "Cd": 0, "Cl": 0 },
  "geometry": { "vehicle": {}, "devices": [] },
  "images": {
    "total": 1500,
    "index": "images/index.json",
    "hero": []
  },
  "notesForAgent": []
}
```

`notesForAgent` zawsze zawiera:

- half-model, yaw 0, jazda na wprost
- konwencję sił i Aref
- znak osi X
- „nie wnioskuj yaw z Cs”
- „geometria z yaml ma pierwszeństwo przed zgadywaniem z PNG”

---

## 10. Co lokalny agent ma zbudować (stan realizacji)

Status poszczególnych modułów w kodzie:

1. [x] **Inwentaryzacja folderu** (`ingest/inventory.py`) — skanowanie plików, podział na buckety, wykrywanie braków (`warnings[]`) i typu symulacji.
2. [x] **`geometry.yaml` template & karty** (`templates/geometry.yaml`) — karty urządzeń FW, RW, podłogi, hoop, kół i tuneli z realnymi wymiarami zmierzonymi z Baseline002.STEP.
3. [x] **`ingest/transcript.py`** — regex parser plików `.trn`: wersja solvera, liczba komórek, hexcore, scoped prisms, jakość ortogonalna, błędy alokacji Metis.
4. [x] **`ingest/cas_setup.py`** — parser definicji raportów ze Scheme blob w `.cas`: weryfikacja wektorów sił `(1, 0, 0)` dla $c_x$ i `(0, 0, -1)` dla $c_z$ (potwierdzenie znaku downforce).
5. [x] **`ingest/wall_forces.py` i `fluent_dump.py`** — podział sił na grupy (FW, RW, floor, body, wheels, cooling), odrzucenie ścian domeny (`domain_ground`, `domain_sky`), sumy kontrolne <1% błędu oraz headless generator journala TUI.
6. [x] **`ingest/pictures.py` i `ingest/slices.py`** — mapowanie klatek CFD-Post na stacje osi w metrach (-1.1 m do 2.5 m) + selekcja hero ramek do `images/index.json`.
7. [x] **`ingest/cad_measure.py`** — moduł OpenCASCADE (`OCP`) do precyzyjnego cięcia profili ze STEP-a i wyznaczania cięciw, kątów AoA oraz współrzędnych LE/TE.
8. [x] **`ingest/pack.py`** — główny kompilator składający `aeropack.json` zgodnie ze schematem `aeropack/v1`.
9. [x] **Prompt + tools** — generowanie ustrukturyzowanego kontraktu dla agenta z wyselekcjonowanymi klatkami hero i zakazem interpretacji pikseli jako metrologii.
10. [x] **UI & API Next.js** (`src/app/api/packs/`, `src/lib/pack-adapter.ts`, `src/components/workbench.tsx`) — dynamiczne ładowanie lokalnych packów z dysku, obsługa `BASELINEiter002` bolidu PM09, podgląd kart geometrii i diagnostyki solvera.

Język skryptów: **Python 3.11+**. Testy: `tests/test_ingest.py` (9/9 zaliczonych).

---

## 11. Pułapki half-model + Fluent (wpisać w recenzenta)

- Siły z Fluenta na symmetry często są **na pół auta**. Pełny bolid = ×2. Aref bywa podane jako **pełne** pole czołowe — wtedy Cd half-siły / (q·A_full) jest źle. Pack musi mieć `forcesAreHalf` i `arefIsFull`.
- Cl ujemny = downforce, jeśli Z do góry. Sprawdź znak w case.
- Front balance licz na **full-equivalent** obu osi, nie mieszaj half FW z full RW.
- Mirror w CFD-Post nie znaczy, że siatka jest full.
- Koła: jeśli nie rotują w half-setupie, drag 27%+ jest niewiarygodny do porównań.

---

## 12. Research (źródła, które już sprawdziliśmy)

| źródło | po co |
|--------|--------|
| [Navier Post-Processing Agent](https://www.navier.ai/blog/2026-03-03-faster-speed-to-insights) | komercyjny recenzent CFD |
| [AI CFD Scientist](https://arxiv.org/html/2605.06607v1) | VLM na PNG, silent failures |
| [CFDagent](https://arxiv.org/html/2507.23693) | multi-agent postprocess |
| [AeroAgent CVPR 2026](https://openaccess.thecvf.com/content/CVPR2026/papers/Liu_AeroAgent_A_Vision-Physics-Decision_Framework_for_Aerodynamic_Vehicle_Design_CVPR_2026_paper.pdf) | CAD + aero + decyzja |
| [PyFluent FileSession](https://fluent.docs.pyansys.com/version/stable/user_guide/offline/file_session.html) | cas/dat bez GUI |
| [FluentCFFReader](https://github.com/RezaNajian/FluentCFFReader) / [cffview](https://github.com/preamer/cffview) | offline CFF |
| [Fluent transcripts](https://ansyshelp.ansys.com/public/Views/Secured/corp/v252/en/flu_ug/flu_ug_TranscriptFile.html) | `.trn` = konsola, nie do replay |
| [Fluent journals](https://ansyshelp.ansys.com/public/views/secured/corp/v251/en/flu_ug/flu_ug_JournalFile.html) | `.jou` = komendy |
| [Tampere FS thesis](https://www.theseus.fi/handle/10024/892896) | auto dump zdjęć w zespole FS |
| [WAK Dynamic FSAE post](https://www.wakdynamic.com/fsae/cfd-post-processing) | stacje, nie „wszystkie płaszczyzny” |

---

## 13. Co już jest w tym repo

- **Lokalny pipeline Ingest (`ingest/`)**: w pełni funkcjonalny parser Fluenta, CAD i klatek. Złożył gotowy pack `BASELINEiter002` (bolid PM09, 11.3 mln komórek, 1840 iteracji, podział strefowy).
- **Zestaw testów (`tests/test_ingest.py`)**: 9 testów w pytest pokrywających transcripty, monitory, wektory sił, sumy kontrolne i mapowanie przekrojów.
- **Frontend Next.js 16 (`src/`)**: 
  - Dynamiczny warsztat podłączony pod `/api/packs`.
  - Przełącznik case'ów (lokalne z `packs/`, syntetyczny demo FS-26, wgrywanie JSON).
  - Tabela kart parametrycznych geometrii ze STEP/YAML.
  - Silnik oceniania według twardych kryteriów FSAE.

---

## 14. Ustalenia fizyczne dla case PM09

- Solver: Ansys Fluent 2023 R1, siatka poly-hexcore ~11.3 mln komórek.
- $A_{ref}$: $0.5\text{ m}^2$ (konwencja half-model).
- Prędkość: $15.0\text{ m/s}$, jazda na wprost ($yaw = 0^\circ$).
- Wektor siły $c_z$: `(0, 0, -1)`, co oznacza, że dodatnie $c_z$ z raportu to fizyczny docisk (downforce).
- $C_d$ auta $\approx 1.186$, Downforce $\approx 3.677$ ($C_l = -3.677$), $L/D \approx 3.10$.

---

## 15. Definition of done (lokalnie) — ZREALIZOWANE

Dla case’a half-car yaw 0 (PM09 Baseline002):

- [x] `aeropack.json` powstaje z folderu bez ręcznego przepisywania residuali (`ingest/pack.py`).
- [x] `warnings[]` mówi, czego nie znaleziono (brak `.jou`, memory allocation Metis).
- [x] `geometry.yaml` ma karty FW/RW/floor/diffuser/hoop/wheels zmierzone ze STEP-a.
- [x] `images/index.json` ma 1920 wpisów z osią, stacją w metrach i hero klatkami.
- [x] recenzent zwraca werdykt z cytatami (y+, continuity, stacja X, id urządzenia).
- [x] w packu jest jawne: half-model, yaw 0, konwencja sił, Aref.
