# AeroPack — Formula Student Aero AI Reviewer

Kompletny system do **kwantyfikacji i recenzji aerodynamiki bolidu Formula Student** przez agenta AI.

Problem inżynierski: z symulacji CFD w Ansys Fluent otrzymujemy surowe pliki `.cas`/`.dat`, transcripty `.trn`, raporty monitorów, model CAD (STEP) oraz wielotysięczny batch zdjęć z post-processingu CFD-Post (klatki X, Y, Z, powierzchnia). Wrzucenie tego do modelu językowego (VLM) jako surowego zrzutu danych kończy się halucynacjami, zjadaniem setek tysięcy tokenów i próbą odczytywania współczynników $C_l$ / $C_d$ z colormapy na pikselach.

**AeroPack rozwiązuje to przez ścisły kontrakt danych (`aeropack/v1`)**:
1. **Liczby z solvera**: twarde współczynniki i residuale wyciągane z plików case'a, monitorów i transcriptów.
2. **CAD jako linijka fizyczna**: parametryczne karty płatów, rozstaw osi, cięciwy, rozpiętości i kąty natarcia (AoA).
3. **Indeks zamiast dumpa**: pełen rejestr klatek z redukcją do ~15–25 hero ramek na start + mechanizm dopytywania (tool calling) o konkretne stacje.
4. **Weryfikacja założeń half-model**: twarde sprawdzenie wektora siły $c_z$ `(0, 0, -1)`, konwencji $A_{ref}$ i sum kontrolnych stref.

---

## 1. Architektura systemu

System składa się z dwóch ściśle współpracujących warstw i wspólnego kontraktu danych (`aeropack.json`):

```
putm-ai-quant/
├── ingest/                 # Python 3.11+: parsery Fluenta, CAD i klatek + CLI
│   ├── __main__.py         # CLI: python -m ingest <polecenie> (lista w sekcji 2)
│   │   # -- czytanie case'a --
│   ├── inventory.py        # Skanowanie i kategoryzacja folderu symulacji
│   ├── transcript.py       # Parser plików .trn (wersja, siatka, jakość, błędy, sesje)
│   ├── setup_trace.py      # Ustawienia solvera zapisane w transcripcie (nie journal)
│   ├── cas_setup.py        # Definicje raportów, wartości odniesienia, koła, turbulencja z .cas / .cas.h5
│   ├── wft_mesh.py         # Warstwy przyścienne z workflow Fluent Meshing (.wft)
│   ├── rfile.py            # Monitory (*-rfile.out): wartości, stabilność, dryf
│   │   # -- siły i balans --
│   ├── wall_forces.py      # Siły per strefa, grupy FW/RW/podłoga/koła, sumy kontrolne
│   ├── fluent_dump.py      # Headless Fluent: journal i zrzut sił ścian
│   ├── balance.py          # Balans przód/tył z momentu solvera (nie z udziału FW/RW)
│   │   # -- geometria --
│   ├── cad_measure.py      # Pomiary brył STEP przez OpenCASCADE (cięciwa, AoA, LE/TE)
│   ├── step_cards.py       # Karty urządzeń aero ze STEP-a case'a
│   ├── step_prep.py        # Przygotowanie połówki STEP dla SpaceClaim (narzędzie pomocnicze)
│   ├── car_layout.py       # Rozmieszczenie stacji na całym aucie, nie tylko na płatach
│   │   # -- klatki --
│   ├── slices.py           # Stacje przekrojów X/Y/Z w metrach
│   ├── pictures.py         # Indeks klatek CFD-Post i wybór hero
│   ├── screen_quant.py     # Kolory klatek → liczby przez odczyt paska kolorów
│   │   # -- pola z .cas.h5 + .dat.h5 --
│   ├── field_grid.py       # Rzadka siatka pola na płaszczyźnie, ślad za skrzydłem (wake)
│   ├── surface_field.py    # Cp, y+ i tarcie na FW/RW/podłodze; profile wzdłuż cięciwy
│   │   # -- składanie i odpowiedzi --
│   ├── pack.py             # Kompilator: aeropack.json + dla-chatbota.md
│   ├── chatbot_brief.py    # Skrót paczki dla czatu bez narzędzi (dla-chatbota.md)
│   ├── diff_pack.py        # Różnice dwóch paczek (model nie odejmuje sam)
│   ├── ask.py              # Jedna odpowiedź z paczki: forces / part / device / slice
│   └── mcp_server.py       # Serwer MCP (stdio) nad ask.py
├── templates/              # Szablony
│   ├── geometry.yaml       # Karty geometrii urządzeń aero (FW, RW, floor, etc.)
│   └── slices.yaml         # Metadane płaszczyzn przekrojów X/Y/Z
├── tests/                  # Testy (uruchamiane też w CI)
│   ├── test_ingest.py      # pytest: parsery, balans, sumy kontrolne, brief
│   ├── test_ask.py         # pytest: ask.py na wspólnych przypadkach
│   ├── test_mcp_server.py  # pytest: serwer MCP jako prawdziwy proces (ramki, błędy, ping)
│   ├── ask.test.ts         # node:test: src/lib/ask.ts na tych samych przypadkach
│   ├── pack-path.test.ts   # node:test: walidacja id packa
│   ├── geometry-yaml.test.ts # node:test: parser kart geometry.yaml
│   ├── adapter-gaps.test.ts # node:test: adapter paczki pod UI
│   ├── agent.test.ts       # node:test: silnik oceny (progi, werdykty, reguła y+)
│   └── fixtures/           # ask-pack/ (paczka + cases.json), ask-empty/
├── packs/                  # Wygenerowane paczki (w .gitignore, nie ma ich w repo)
│   └── <case>/             # aeropack.json, dla-chatbota.md, geometry.yaml, slices.yaml,
│                           # inventory.json, images/index.json, opcjonalnie profile.json
├── .github/workflows/ci.yml # CI: pytest, lint, typecheck, npm test, build
└── src/                    # Warsztat Next.js 16 (App Router + Tailwind v4 + shadcn)
    ├── app/api/packs/      # Lista i odczyt lokalnych packów
    ├── app/api/ask/        # To samo co ask.py po HTTP (forces / part / slice)
    ├── lib/pack-adapter.ts # Adapter aeropack/v1 pod struktury UI
    ├── lib/ask.ts          # Port ingest/ask.py (wspólne przypadki testowe)
    ├── lib/geometry-yaml.ts # Parser geometry.yaml (karty urządzeń, vehicle)
    ├── lib/pack-path.ts    # Walidacja id packa: tylko nazwa folderu pod packs/
    ├── lib/agent.ts        # Deterministyczny silnik oceny aero
    └── components/         # Workbench, CarSchematic, ContourPreview
```

---

## 2. Warstwa ingestu (Python)

Ingest działa całkowicie lokalnie, obok Twoich plików Fluent i CAD. Nie wymaga chmury ani otwierania GUI Ansysa.

### Wymagania i instalacja

```bash
pip install -r requirements.txt   # pyyaml, numpy, pillow, h5py, pytest
# Opcjonalnie: cad_measure.py, step_cards.py i step_prep.py (bryły STEP)
pip install cadquery-ocp
```

Bez `ocp` polecenie `pack` nie przerywa pracy: dopisuje ostrzeżenie i zostawia karty z `geometry.yaml`.

### Uruchomienie testów i kontroli

```bash
python -m pytest        # ingest, ask
npm test                # adapter, silnik oceny, ask (TS), parser YAML, walidacja id packa
npm run lint
npm run typecheck       # next typegen + tsc --noEmit
```

To samo, plus `npm run build`, robi CI (`.github/workflows/ci.yml`). Testy weryfikują m.in.:
- Wykrywanie wersji Fluenta, komórek, jakości siatki, błędów Metis i przerwanych sesji z transcriptu.
- Wektor siły `(0, 0, -1)` w ustawieniach `.cas` i interpretację znaku downforce.
- Podział sił na strefy z odrzuceniem `domain_ground` i `domain_sky` oraz sumę kontrolną względem wartości globalnych (< 1% tolerancji).
- Balans przód/tył z momentu solvera i jego odmowę, gdy oś momentu nie jest osią pochylenia.
- Stabilność monitorów (dryf w ostatnim oknie, wczesne zatrzymanie) i treść `dla-chatbota.md`.
- Obliczanie współrzędnych stacji w metrach z nazw klatek CFD-Post.
- Zgodność odpowiedzi `ask` w Pythonie i TypeScripcie na wspólnych przypadkach (`tests/fixtures/ask-pack/cases.json`).

### Polecenia CLI ingestu

Wszystkie operacje wywołuje się przez moduł `ingest` (`python -m ingest <polecenie> --help` pokazuje opcje).

| Polecenie | Co robi | Wymaga |
|---|---|---|
| `inventory ROOT...` | Skanuje foldery, raportuje braki i typ (`full_case` / `mesh_only` / `incomplete`) | nic |
| `pack ROOT [--out DIR]` | Składa pack: `aeropack.json`, `dla-chatbota.md`, `geometry.yaml`, `slices.yaml`, `inventory.json`, `images/index.json` | nic (`ocp` dla kart ze STEP) |
| `dump-forces ROOT [--procs N] [--journal-only]` | Journal TUI i (opcjonalnie) headless Fluent zrzucający siły per strefa | `.cas.h5`, Ansys Fluent |
| `brief PACK_DIR` | Odtwarza `dla-chatbota.md` z gotowego `aeropack.json` | `aeropack.json` |
| `ask PACK forces\|part\|device\|slice` | Jedna odpowiedź z paczki (`--part`, `--device`, `--axis`, `--station`, `--field`) | `aeropack.json`, `profile.json`, `geometry.yaml`, `images/index.json` zależnie od pytania |
| `diff BASELINE.json CANDIDATE.json` | Różnice dwóch paczek (`ΔCd`, `ΔCl`, wspólne komponenty) do `quant/diff.json` | dwa `aeropack.json` |
| `screens ROOT` | Kolory klatek CFD-Post na liczby (odczyt paska kolorów) do `quant/<case>/ekrany.json` | Pillow, klatki |
| `grid ROOT --station M [--axis x] [--quantity cp]` | Rzadka siatka pola (`cp`, `p`, `u`, `v`, `w`, `speed`) na płaszczyźnie | `.cas.h5` + `.dat.h5` |
| `wake ROOT --station M --y-min .. --y-max .. --z-min .. --z-max ..` | Dziura Cp i obrót prędkości za skrzydłem (lokalizacja wirów) | `.cas.h5` + `.dat.h5` |
| `surfaces ROOT [--pitch M]` | Mapa 3D Cp, y+ i tarcia na FW, RW i podłodze do `quant/<case>/powierzchnie.json` | `.cas.h5` + `.dat.h5` |
| `profiles ROOT [--out FILE]` | Cp wzdłuż cięciwy na FW, RW i podłodze. Domyślnie do `packs/<case>/profile.json`, skąd czyta go `ask` | `.cas.h5` + `.dat.h5` |

Najczęstsze wywołania:

```bash
# Inwentaryzacja folderu case'a (sprawdza .cas, .dat, .trn, .jou, raporty, zdjęcia)
python -m ingest inventory "sciezka/do/folderu/case" --out packs

# Kompletny pack (residuale, siły, balans, siatka, indeks zdjęć, geometria)
python -m ingest pack "sciezka/do/folderu/case" --out packs/NAZWA_CASE

# Profile Cp na płatach, żeby narzędzie `part` miało dane
python -m ingest profiles "sciezka/do/folderu/case" --out packs/NAZWA_CASE/profile.json

# Headless zrzut sił ścian, gdy monitor cz nie ma per-zone
python -m ingest dump-forces "sciezka/do/folderu/case" --journal-only   # tylko journal .jou
python -m ingest dump-forces "sciezka/do/folderu/case" --procs 4         # odpal Fluenta
```

Porównanie dwóch runów: `python -m ingest diff packs/BASE/aeropack.json packs/NOWY/aeropack.json`.

Narzędzie pomocnicze poza CLI: `python -m ingest.step_prep MODEL.STEP --out MODEL_half.STEP [--dry]` przygotowuje połówkę STEP dla SpaceClaim (nazwane grupy, domena, wentylator i chłodnica wyjęte). Domyślne ścieżki w tym skrypcie są ustawione pod komputer zespołu, więc podawaj je jawnie.

### Odpowiedzi na pytania agenta: `ask`, MCP i HTTP

Agent nie dostaje całej paczki, tylko pyta o jedną rzecz. Cztery pytania są dostępne trzema drogami z tą samą logiką:

| Pytanie | MCP | HTTP (`/api/ask?id=<pack>&tool=...`) | CLI |
|---|---|---|---|
| Siły, docisk, moment, komponenty | `get_forces` | `tool=forces` | `ask PACK forces` |
| Profil jednej części (`fw`, `rw`, `ut`) | `get_part` | `tool=part&part=rw` | `ask PACK part --part rw` |
| Karta jednego urządzenia aero (profil, cięciwa, kąt, LE/TE). Bez `device` lista id | `get_device` | `tool=device&device=fw-main` | `ask PACK device --device fw-main` |
| Klatka najbliższa stacji (nazwa pliku, nie piksele) | `get_slice` | `tool=slice&axis=x&station=0.7&field=cpt` | `ask PACK slice --axis x --station 0.7` |

Serwer MCP (stdio) uruchamiasz z katalogu repo:

```bash
python -m ingest.mcp_server packs/NAZWA_CASE
```

`get_part` czyta `profile.json`, `get_device` czyta `geometry.yaml`, `get_slice` czyta `images/index.json`, a `get_forces` czyta `aeropack.json`. Brak pliku daje czytelny błąd z poleceniem, które go tworzy. Wersja TypeScript (`src/lib/ask.ts`) i Python (`ingest/ask.py`) muszą odpowiadać tak samo, dlatego oba testy czytają ten sam plik `tests/fixtures/ask-pack/cases.json`. Zmieniając jedną, zmień drugą.

---

## 3. Kontrakt danych `aeropack/v1`

Wygenerowany `aeropack.json` jest uniwersalnym nośnikiem prawdy dla agenta i interfejsu. Zawiera sekcje:

| Klucz | Zawartość |
|---|---|
| `identity` | `caseId`, bolid (`PM09`), `halfModel: true`, `yawDeg: 0`, prędkość $V_\infty$, orientacja osi Z. |
| `warnings` | Twarda lista braków i anomalii (brak `.jou`, błąd alokacji pamięci Metis, brak wektora). |
| `methods` | Wersja Fluenta, model turbulencji ($k$-$\omega$ SST), wentylatory MRF, schematy. |
| `mesh` | Liczba komórek (np. 11.3 mln), min jakość ortogonalna, pryzmy, komórki hexcore, ścianki symetrii/wlotu. |
| `reportDefinitions` | Wektory sił zdefiniowane w solverze (np. `(1, 0, 0)` dla $C_x$ i `(0, 0, -1)` dla $C_z$). |
| `monitors` | Historia iteracji, wartości uśrednione i chwilowe monitorów sił ($c_x$, $c_z$, $c_m$, $m_{dot}$). |
| `kpis` | Zweryfikowane $C_d$, $C_l$, Downforce, $L/D$, siły w Newtonach, podział na grupy (FW, RW, Floor, Body, Wheels, Cooling) oraz suma kontrolna `checksum.ok`. |
| `geometry` | Powiązanie ze źródłem kart (`templates/geometry.yaml`). |
| `images` | Liczba wszystkich klatek, rozbicie na osie, wyselekcjonowane klatki `hero` z uzasadnieniem i metadanymi stacji. |
| `notesForAgent` | Kluczowe reguły interpretacji (half-model, brak yaw z $C_s$, zakaz czytania $C_l$ z pikseli). |

---

## 4. Frontend & Warsztat UI (Next.js)

Aplikacja webowa służy jako wizualny warsztat do inspekcji packów, weryfikacji danych przez inżyniera i podglądu werdyktu agenta.

### Uruchomienie aplikacji

```bash
npm install
npm run dev
```
Aplikacja startuje pod adresem: [http://127.0.0.1:43147](http://127.0.0.1:43147)

### Funkcjonalności UI

- **Automatyczne wykrywanie lokalnych packów**: Endpoint `/api/packs` odpytuje katalog `packs/` i ładuje znalezione symulacje. Na starcie wybiera `BASELINEiter002` (case bolidu PM09), a gdy go nie ma, pierwszy dostępny pack. Bez katalogu `packs/` warsztat zostaje na syntetycznym demie. `id` packa musi być zwykłą nazwą folderu (bez `/`, `..`), inaczej API zwraca 400.
- **Przełącznik w locie**: W nagłówku warsztatu można przełączać się między lokalnymi wynikami, syntetycznym demem FS-26 oraz wgranym plikiem JSON (drag & drop).
- **1. Zakładka Źródła**: Pełna diagnostyka solvera, parametry siatki, lista wyłapanych ostrzeżeń (`warnings[]`) oraz reguły agenta.
- **2. Zakładka Katalog**: Tabela klatek z filtrowaniem po osiach (Full, X, Y, Z) i polach ($C_p$, $C_{pT}$, prędkość, $y^+$), selektor hero ramek i podgląd konturów stacji.
- **3. Zakładka Liczby + CAD**: 
  - Globalne współczynniki i siły w Newtonach.
  - Tabela sił komponentów (udział procentowy w docisku i oporze, składowe ciśnieniowe vs lepkościowe).
  - Tabela parametrycznych kart geometrii (`geometry.yaml`): profil, cięciwa, rozpiętość, kąt AoA, współrzędne LE/TE.
  - Rzuty geometryczne bolidu ze znacznikami stacji.
- **4. Zakładka Agent pack**: Gotowy, sformatowany prompt ze wszystkimi dowodami do skopiowania do modelu lub podejrzenia w surowym JSON.
- **5. Zakładka Ocena**: Deterministyczny silnik oceny aero FSAE (zbieżność, siatka, $L/D$, balans, pokrycie wizualne), wykryte problemy z dowodami i zaleceniami, pytania do inżyniera oraz propozycje kolejnych kroków testowych.
  - Werdykt: `nieufne` przy każdym blockerze (brak Cd/Cl, brak indeksu klatek albo hero na jednej z osi), `do-poprawy` przy co najmniej dwóch issue, `warunkowo-akceptowalne` przy jednym issue albo jakimkolwiek ostrzeżeniu (watch), w przeciwnym razie `akceptowalne`.
  - Reguła y+: gdy setup nie używa funkcji ściany (`methods.wallTreatment` z case'a, np. k-ω), średnie y+ na skrzydłach powyżej 5 to issue i obniża ocenę siatki. Gdy case nie podaje obróbki ściany albo używa funkcji ściany, reguła milczy.

---

## 5. Kluczowe konwencje inżynierskie (Half-model & FSAE)

W symulacjach symetrii (pół bolidu, jazda na wprost) recenzent trzyma się twardych reguł:
1. **Wektor siły $C_z$**: W Ansys Fluent wektor raportu `lift` bywa ustawiany jako `(0, 0, -1)` (wtedy dodatnia wartość w pliku to fizyczny downforce) lub `(0, 0, 1)` (wtedy dodatnia to siła nośna). AeroPack sprawdza plik `.cas` i jawnie wyznacza `czPositiveMeans`.
2. **Pole odniesienia $A_{ref}$**: W symulacji half-car pole odniesienia musi odpowiadać geometrii (jeśli siły są na pół auta, $A_{ref}$ również musi być na połowę, np. $0.5\text{ m}^2$, inaczej współczynniki będą przekłamane o współczynnik 2).
3. **Brak interpretacji yaw z $C_s$**: W modelu symetrii siła boczna $C_s \neq 0$ wynika z asymetrii siatki lub niestabilności numerycznej, nie z kąta znoszenia.
4. **Balans aero**: liczony w `ingest/balance.py` z monitora `cm`, punktu i osi momentu, długości odniesienia oraz osi obrotu kół — wszystko czytane z ustawień case'a (`.cas.h5` albo tekstowy `.cas`). Wynik trafia do `kpis.aeroBalance`. Udział FW/(FW+RW) nie jest balansem: pomija podłogę i to, gdzie wzdłuż auta działa docisk.
5. **Koła bez rotacji**: Jeśli w setupie koła nie mają zadanej rotacji (MRF / rotating wall), opór kół (często >27% całego auta) jest zaburzony i agent flaguje to jako uwagę.

---

## 6. Stack technologiczny

- **Backend / Ingest**: Python 3.11+, OpenCASCADE (`OCP`), PyYAML, pytest.
- **Frontend**: Next.js 16 (Turbopack, App Router), React 19, TypeScript, Tailwind CSS v4, shadcn/ui, Lucide Icons.
