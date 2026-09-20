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

System składa się z dwóch ściśle współpracujących warstw:

```
fsae-ai-quant/
├── ingest/                 # Python 3.11+: parser Fluenta, CAD i klatek
│   ├── inventory.py        # Skanowanie i kategoryzacja folderu symulacji
│   ├── transcript.py       # Regex parser plików .trn (wersja, siatka, błędy)
│   ├── cas_setup.py        # Ekstrakcja definicji raportów i wektorów sił z .cas
│   ├── rfile.py            # Parser plików monitorów (*-rfile.out)
│   ├── wall_forces.py      # Ekstrakcja sił per strefa, sumy kontrolne, odcięcie tunelu
│   ├── cad_measure.py      # Pomiary cięciw, kątów AoA i LE/TE ze STEP przez OpenCASCADE
│   ├── slices.py           # Definicje stacji i zakresów współrzędnych
│   ├── pictures.py         # Indeksowanie batcha zdjęć i wybór hero klatek
│   ├── fluent_dump.py      # Headless Fluent runner (generowanie i zrzut sił ścian)
│   └── pack.py             # Główny kompilator składający aeropack.json
├── templates/              # Źródła prawdy i szablony
│   ├── geometry.yaml       # Karty geometrii urządzeń aero (FW, RW, floor, etc.)
│   └── slices.yaml         # Metadane płaszczyzn przekrojów X/Y/Z
├── tests/                  # Testy jednostkowe parserów i konwersji
│   └── test_ingest.py      # 9 testów pytest weryfikujących numerykę i wektory
├── packs/                  # Wygenerowane paczki symulacji (np. BASELINEiter002)
│   └── BASELINEiter002/    # aeropack.json, geometry.yaml, index zdjęć
└── src/                    # Warsztat Next.js 16 (App Router + Tailwind v4 + shadcn)
    ├── app/api/packs/      # Endpoint API skanujący i serwujący lokalne packi
    ├── lib/pack-adapter.ts # Adapter formatu aeropack/v1 pod struktury UI
    └── components/         # Workbench, CarSchematic, ContourPreview
```

---

## 2. Warstwa ingestu (Python)

Ingest działa całkowicie lokalnie, obok Twoich plików Fluent i CAD. Nie wymaga chmury ani otwierania GUI Ansysa.

### Wymagania i instalacja

```bash
pip install -r requirements.txt
# Opcjonalnie do cad_measure.py (analiza brył STEP):
# pip install ocp pyyaml regex
```

### Uruchomienie testów

```bash
python -m pytest
```
Wszystkie 9 testów jednostkowych weryfikuje m.in.:
- Wykrywanie wersji Fluenta, komórek, jakości siatki i błędów Metis z transcriptu.
- Weryfikację wektora siły `(0, 0, -1)` w Scheme blob `.cas` i interpretację znaku downforce.
- Podział sił na strefy z odrzuceniem `domain_ground` i `domain_sky`.
- Zgodność sumy kontrolnej sił stref względem wartości globalnych (< 1% tolerancji).
- Obliczanie współrzędnych stacji w metrach z nazw klatek CFD-Post.

### Polecenia CLI ingestu

Wszystkie operacje wywołuje się przez moduł `ingest`:

#### 1. Inwentaryzacja folderu case'a
Skanuje folder, sprawdza obecność plików `.cas`, `.dat`, `.trn`, `.jou`, raportów i zdjęć, raportując braki:
```bash
python -m ingest inventory "sciezka/do/folderu/case" --out packs
```

#### 2. Złożenie kompletnego `aeropack.json`
Przetwarza cały case, weryfikuje wektory, wyciąga residuale, indeksuje zdjęcia i tworzy gotowy pack:
```bash
python -m ingest pack "sciezka/do/folderu/case" --out packs/NAZWA_CASE
```

#### 3. Headless zrzut sił ścian z Fluenta (opcjonalnie)
Jeśli monitor `cz` miał wyłączone `per-zone? #f` i nie masz zrzutu sił per komponent, skrypt generuje journal TUI i opcjonalnie odpala Ansys Fluent w trybie batch/headless:
```bash
# Tylko wygeneruj journal .jou bez uruchamiania solvera:
python -m ingest dump-forces "sciezka/do/folderu/case" --journal-only

# Odpal Fluent headless na 4 rdzeniach i zrzuć siły automatycznie:
python -m ingest dump-forces "sciezka/do/folderu/case" --procs 4
```

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

- **Automatyczne wykrywanie lokalnych packów**: Endpoint `/api/packs` automatycznie odpytuje katalog `packs/` i ładuje znalezione symulacje (np. realny case `BASELINEiter002` bolidu PM09).
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

---

## 5. Kluczowe konwencje inżynierskie (Half-model & FSAE)

W symulacjach symetrii (pół bolidu, jazda na wprost) recenzent trzyma się twardych reguł:
1. **Wektor siły $C_z$**: W Ansys Fluent wektor raportu `lift` bywa ustawiany jako `(0, 0, -1)` (wtedy dodatnia wartość w pliku to fizyczny downforce) lub `(0, 0, 1)` (wtedy dodatnia to siła nośna). AeroPack sprawdza plik `.cas` i jawnie wyznacza `czPositiveMeans`.
2. **Pole odniesienia $A_{ref}$**: W symulacji half-car pole odniesienia musi odpowiadać geometrii (jeśli siły są na pół auta, $A_{ref}$ również musi być na połowę, np. $0.5\text{ m}^2$, inaczej współczynniki będą przekłamane o współczynnik 2).
3. **Brak interpretacji yaw z $C_s$**: W modelu symetrii siła boczna $C_s \neq 0$ wynika z asymetrii siatki lub niestabilności numerycznej, nie z kąta znoszenia.
4. **Koła bez rotacji**: Jeśli w setupie koła nie mają zadanej rotacji (MRF / rotating wall), opór kół (często >27% całego auta) jest zaburzony i agent flaguje to jako uwagę.

---

## 6. Stack technologiczny

- **Backend / Ingest**: Python 3.11+, OpenCASCADE (`OCP`), PyYAML, pytest.
- **Frontend**: Next.js 16 (Turbopack, App Router), React 19, TypeScript, Tailwind CSS v4, shadcn/ui, Lucide Icons.
