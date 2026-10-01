# AeroPack: jak to działa

Ten plik jest dla człowieka, nie dla programisty. Opisuje po kolei, po co jest ten projekt, co robi, jak go używać i czego nie potrafi. Szczegóły techniczne są w `README.md`.

## 1. Po co to jest

Robisz symulację aerodynamiki bolidu we Fluencie. Wychodzą z niej gigabajty plików i około 1900 zdjęć z CFD-Post. Nikt (ani człowiek, ani chatbot) nie jest w stanie tego przejrzeć i szybko powiedzieć: „ta symulacja jest wiarygodna, a docisk robi głównie podłoga”.

Ten projekt **czyta pliki symulacji automatycznie, zamienia je na liczby, obrazki i krótkie opisy, ocenia wiarygodność i pozwala o wszystko zapytać**. Nie liczy aerodynamiki. Odczytuje ją i sprawdza.

## 2. Co wchodzi

Folder jednej symulacji. Wystarczą pliki modelu:

- `.cas.h5` (ustawienia i siatka) i `.dat.h5` (końcowy stan przepływu w całej objętości). To jest **jedyne, co jest naprawdę potrzebne**.
- Mogą być dodatkowo: logi solvera `.trn`, pliki z wykresami sił `-rfile.out`, `.wft` (przepis na warstwy przyścienne), geometria `.step`, zdjęcia z CFD-Post. Gdy są, raport jest dokładniejszy. Gdy ich nie ma, program liczy zamiast nich z plików modelu i oznacza, co jest przybliżeniem.
- `.scdoc` (SpaceClaim) jest zamkniętym formatem i nie jest czytany. Geometrię bierze się z `.step`. `.cdat` to ten sam wynik w starszym formacie, więc nie jest potrzebny.

Bolid jest liczony jako **połowa** (symetria), jazda na wprost, 15 m/s. Program rozpoznaje połowę sam, po płaszczyźnie symetrii w siatce.

## 3. Co program robi, po kolei

1. **Ustawienia.** Z `.cas.h5`: model turbulencji, prędkość, obrót kół, wartości odniesienia.
2. **Siły na każdą część bolidu.** Z ciśnienia i tarcia na każdej ściance, bez uruchamiania Fluenta. Suma zgadza się z monitorem Fluenta co do 0,02% (Baseline002).
3. **Stabilność liczenia.** Residua (historia z `.dat.h5`), bilans masy (czy tyle powietrza wchodzi, ile wychodzi), stabilność sił. Z plików `.out` dokładnie, bez nich przybliżenie z różnicy między wartością chwilową a średnią.
4. **Siatka i ściana.** Liczba komórek, y+ (jak blisko ściany jest pierwsza warstwa), wysokość pierwszej komórki zmierzona z siatki, przybliżona jakość siatki.
5. **Oderwania.** Miejsca, gdzie przepływ tuż przy ścianie płynie do przodu auta, czyli powierzchnia przestaje prowadzić powietrze.
6. **Przekroje w poprzek auta.** Strata energii powietrza, wiry (położenie, siła, dokąd lecą), ślad za kołami.
7. **Obrazki.** Przekroje w tych samych 150 płaszczyznach na oś co w CFD-Post, z suwakiem w przeglądarce, oraz widoki Cp, tarcia i y+ na samym aucie.
8. **Ocena wiarygodności** względem literatury (patrz punkt 5).

Wynik trafia do **paczki** w folderze `packs/<nazwa>/`.

## 4. Co dostajesz

Jedno polecenie na folder symulacji:

```bash
python -m ingest report "folder/z/symulacją" --out packs/NAZWA
```

Nic nie trzeba wpisywać ani klikać. Dostajesz pliki:

| Plik | Co to jest |
| --- | --- |
| `SKROT.md` / `SKROT.html` | Jedna strona: werdykt, najważniejsze liczby, skąd się biorą siły, na co uważać, czego brakuje. |
| `PELNY.md` / `PELNY.html` | Absolutnie wszystko: każda strefa, każdy przekrój, każdy wir, ustawienia, residua, metoda liczenia, słowniczek. |
| `WIARYGODNOSC.md` | Ocena 0–100 z uzasadnieniem i źródłami. |
| `obrazy/galeria.html` | Przekroje przepływu z suwakiem. Otwierasz dwuklikiem. |
| `dla-chatbota.md` | Skrót do wklejenia w zwykły czat. |
| `aeropack.json`, `raport.json` | To samo dla programów. |

Dodatkowo:

```bash
# Porównanie dwóch lub więcej symulacji (tabele różnic i wykresy w jednej stronie HTML)
python -m ingest compare packs/NAZWA_A packs/NAZWA_B --out quant/porownanie

# Przeglądarka 3D przepływu (CFD3DViewer): pole, powierzchnia bolidu i linie prądu
python -m ingest viewer "folder/z/symulacją"

# Test niezależności od siatki (potrzebne 2–3 siatki tego samego bolidu)
python -m ingest mesh-study packs/A packs/B packs/C
```

Aplikacja w przeglądarce (warsztat z kartami geometrii i oceną wg reguł FSAE) uruchamia się przez `npm run dev` i otwiera pod adresem http://127.0.0.1:43147. Czyta paczki z folderu `packs/`.

## 5. Metaplik: wszystko w jednym małym folderze

To jest główny cel projektu: zamiast trzymać 16 GB plików CFD-Post i 1920 zdjęć, trzymasz jeden mały folder, z którego da się wszystko odczytać.

```bash
python -m ingest meta "folder/z/symulacją"
```

W środku (`packs/<nazwa>/meta/`):

- `meta.json`: **wszystkie liczby** (siły, y+, oderwania, wiry, residua, ustawienia, ocena wiarygodności), **wnioski** posortowane od najważniejszych (przy każdym napisane, gdzie w pliku leży dowód) i **pochodzenie** każdej liczby (z którego pliku i czy to wartość dokładna, czy przybliżenie). Około 0,25 MB.
- `powierzchnia_1cm.npz` i `powierzchnia_3mm.npz`: mapy ciśnienia, tarcia, y+ i oderwań na aucie, w dwóch rozdzielczościach. Gruba (1 cm) wystarcza do czytania, drobna (3 mm) pokazuje szczeliny między klapami.
- `przekroje.npz`: pola w 150 płaszczyznach na oś, w tych samych miejscach co zdjęcia z CFD-Post.

Razem około 18 MB zamiast 7,6 GB. Z samych tych plików da się narysować obrazki z powrotem (`python -m ingest meta-render`), więc zdjęć nie trzeba przechowywać. `python -m ingest meta-verify` sprawdza, czy nic nie zginęło ani nie zostało uszkodzone.

Dzięki temu agent AI (albo człowiek) czyta najpierw `wnioski`, a potem sięga po konkretną mapę lub liczbę, zamiast przeglądać zdjęcia.

## 6. Jak czytać ocenę wiarygodności

Ocena mówi o dwóch rzeczach:

- **Jak wykonano symulację.** Czy zbiegła się, czy siatka pasuje do modelu turbulencji, czy ziemia i koła się poruszają, czy domena jest dość duża.
- **Czy wyniki leżą tam, gdzie literatura stawia podobne bolidy.** Na przykład udział kół w oporze albo typowy opór i docisk.

Każde sprawdzenie ma wagę, werdykt, wyjaśnienie i źródło (Menter, ANSYS, Celik i Roache, Katz i inne). Wynik liczy się tylko z tych sprawdzeń, które dało się wykonać. **Pokrycie** mówi, jaka część wagi to była. Wysoka ocena przy niskim pokryciu znaczy „nic złego nie znaleziono, ale mało sprawdzono”.

**Czego ocena nie mówi: czy symulacja zgadza się z rzeczywistością.** Do tego trzeba pomiaru z tunelu lub toru. Jeśli go masz, wpisz w plik `pomiary.json` obok symulacji:

```json
{ "CdA_m2": 1.5, "ClA_m2": 4.2, "przod_masa_pct": 47, "zrodlo": "tunel, 12.09" }
```

Wtedy ocena porówna wynik z pomiarem i doda sprawdzenie balansu względem rozkładu masy.

## 7. Na co uważać

- **Porównywać można tylko symulacje liczone tak samo.** Inny model turbulencji albo inna ściana to inna metoda, a nie inny bolid. Program ostrzega o tym w porównaniu i w teście siatki.
- **Niedokończone liczenie** to najczęstsze źródło złych wniosków. Raport pokazuje to na czerwono.
- **Test siatki wymaga trzech siatek.** Bez niego nie wiadomo, o ile wynik zmieniłby się na gęstszej. To zwykle największa niewiadoma.
- **Jakość siatki bez logu jest przybliżona.** Przesadza w skrajnie spłaszczonych komórkach (np. przy styku opony z ziemią). Gdy jest log siatkowania, używane są jego liczby.
- **Telemetria z toru** na razie nie jest wpięta w program. Obecne nagrania nie zawierają docisku aerodynamicznego ani skalibrowanej wysokości zawieszenia (szczegóły w README, sekcja 7).
- Program nie ocenia zachowania w zakręcie, bo takich symulacji jeszcze nie ma.

## 8. Co jest w którym folderze

- `ingest/` czyta pliki i liczy (to jest właściwy program),
- `src/` to aplikacja w przeglądarce,
- `templates/` to szablony (płaszczyzny CFD-Post, karty geometrii),
- `tests/` to testy automatyczne (sprawdzają, że to, co liczy program, zgadza się z wartościami o znanym wyniku),
- `packs/` i `quant/` to wyniki (poza gitem).

## 9. Co dalej

Zakręt, kąt znoszenia i różne prędkości, pełny bolid zamiast połowy, telemetria z toru jako punkt odniesienia dla CFD. Szczegóły w `README.md`, sekcja 7.
