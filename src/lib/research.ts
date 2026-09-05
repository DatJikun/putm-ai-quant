export type Source = {
  title: string
  url: string
  year: string
  what: string
  overlap: string
}

export const sources: Source[] = [
  {
    title: "Navier AI — Post-Processing Agent",
    url: "https://www.navier.ai/blog/2026-03-03-faster-speed-to-insights",
    year: "2026",
    what: "Komercyjny agent czyta wyniki CFD/FEA, sam robi slice’y, łapie anomalie, pisze raport. Nie jest to Fluent-cas-dat + 1500 PNG z FS, ale to najbliższy produkt „agent recenzuje post-processing”.",
    overlap: "bliski produkt",
  },
  {
    title: "AI CFD Scientist (OpenFOAM, vision gate)",
    url: "https://arxiv.org/html/2605.06607v1",
    year: "2026",
    what: "Po runie renderer robi PNG, VLM najpierw sprawdza czy obrazek jest czytelny, potem czy fizyka się zgadza. Na 16 podstawionych silent-failures złapał 14. Dokładnie ten mechanizm, którego potrzebujesz na klatkach.",
    overlap: "wzór na VLM",
  },
  {
    title: "CFDagent — GPT-4o multi-agent CFD",
    url: "https://arxiv.org/html/2507.23693",
    year: "2025",
    what: "Preprocess / solver / postprocess agenci. Postprocess wyciąga Cd, Cl, contour, iso, sondy. Walidacja na kuli, nie na bolidzie FS.",
    overlap: "pipeline agentowy",
  },
  {
    title: "AeroAgent (CVPR 2026) — vision–physics–decision",
    url: "https://openaccess.thecvf.com/content/CVPR2026/papers/Liu_AeroAgent_A_Vision-Physics-Decision_Framework_for_Aerodynamic_Vehicle_Design_CVPR_2026_paper.pdf",
    year: "2026",
    what: "Agent łączy obraz, surrogate aero i decyzję projektową dla pojazdów. To pętla projektowa, nie recenzja Twojego Fluent dumpa.",
    overlap: "CAD + aero + agent",
  },
  {
    title: "DrivAerNet++ / multi-agent car design",
    url: "https://api.emergentmind.com/papers/2503.23315",
    year: "2025",
    what: "8000 nadwozi, CAD, siatki, CFD, multi-view. Simulation agent odpytuje bazę albo surrogate. Pokazuje, że CAD i CFD muszą żyć w jednym rekordzie.",
    overlap: "multimodalny rekord auta",
  },
  {
    title: "PyFluent FileSession / CaseFile / DataFile",
    url: "https://fluent.docs.pyansys.com/version/stable/user_guide/offline/file_session.html",
    year: "docs",
    what: "Oficjalny odczyt .cas.h5/.dat.h5 bez odpalania GUI. Stąd siły, pola, siatka. Stary binarny .cas/.dat bez HDF5 jest trudniejszy — lepiej wyeksportować CFF albo EnSight/VTK.",
    overlap: "warstwa liczb z Fluent",
  },
  {
    title: "FluentCFFReader + cffview",
    url: "https://github.com/RezaNajian/FluentCFFReader",
    year: "2025–26",
    what: "Otwarty reader CFF → VTP/VTU. cffview pokazuje ustawienia solvera z HDF5 bez licencji GUI. To droga, gdy nie chcesz trzymać pełnego Fluenta przy agencie.",
    overlap: "offline cas/dat",
  },
  {
    title: "Tampere Formula Student — automatyczny post-process",
    url: "https://www.theseus.fi/handle/10024/892896",
    year: "2025",
    what: "STAR-CCM+, szablon który sam zrzuca dziesiątki (nie tysiące) ujęć. Cel: spójne porównania, nie wrzucanie dumpa do LLM. Dokładnie ten ból FS.",
    overlap: "FS + dump zdjęć",
  },
  {
    title: "WAK Dynamic — FSAE CFD post-processing",
    url: "https://www.wakdynamic.com/fsae/cfd-post-processing",
    year: "praktyka",
    what: "Jak zespół FSAE tnie ślad za kołem: konkretne stacje, nie „wszystkie płaszczyzny”. Katalog 1500 klatek ma sens dopiero po zmapowaniu na takie stacje.",
    overlap: "konwencja płaszczyzn FS",
  },
  {
    title: "CFDInsight (ParaView + OpenFOAM)",
    url: "https://github.com/ArthurLaneri05/CFDInsight",
    year: "2024+",
    what: "Automatyczne siły, slice’y, delta vs baseline. OpenFOAM, ale ten sam kontrakt: stałe kamery, stałe skale, porównywalność.",
    overlap: "reprodukowalny dump",
  },
  {
    title: "HPC + Fluent w zespole Formula Student (MDPI)",
    url: "https://www.mdpi.com/2076-3417/11/14/6552",
    year: "2021",
    what: "Automatyzacja Fluent TUI w prawdziwym zespole FS. KPI aero +6× iteracji. Nie ma agenta, jest argument, że dump musi być powtarzalny.",
    overlap: "Fluent + FS",
  },
  {
    title: "AI-assisted CFD of FSAE wings (GA–ANN)",
    url: "https://doi.org/10.1016/j.ijft.2025.101440",
    year: "2025",
    what: "Optymalizacja kątów płatów FSAE przez CFD + sieć, nie recenzja obrazków. AI w FS aero już jest — jako optimizer, nie jako recenzent case’a.",
    overlap: "AI × FSAE",
  },
]

export const verdict = {
  existsExactClone: false,
  existsPieces: true,
  canQuantify: true,
  doNotDumpRaw:
    "Nie wrzucaj agentowi 1500 PNG ani surowych .cas/.dat. Zrób pack: liczby z solvera, metadata CAD, katalog klatek, 15–30 hero ramek, pytania.",
}
