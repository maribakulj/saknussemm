# Autopilot — la file de travail autonome

Ce fichier est **l'état**, pas un compte rendu. Une session réveillée par la
Routine n'a pas mon contexte : elle a ce fichier, `docs/PLAN.md`, et le dépôt.
Si les trois se contredisent, `docs/PLAN.md` gagne et ce fichier est corrigé.

Dernière mise à jour : 2026-08-16.

---

## Le contrat de boucle — piloté par les événements

**La PR ouverte est l'unité de travail, et « verte » est la condition de
sortie de chaque tour.** La boucle ne tourne plus à l'horloge : elle reprend
sur **événement** de la PR — résultat de CI, commentaire de revue, push,
conflit de merge — et rend la main quand la PR est verte et qu'il n'y a rien
en attente.

**PR courante :** [#77](https://github.com/maribakulj/saknussemm/pull/77),
ouverte le 2026-08-16 depuis `main`, et abonnée. Une PR jumelle vit dans
`cinoc` — [#80](https://github.com/maribakulj/cinoc/pull/80) — et la boucle
surveille les deux : depuis le 2026-08-16 le travail s'étend à trois dépôts,
donc « verte » se qualifie sur chacun de ceux qu'un geste touche.

Quand une PR est mergée, la souscription meurt avec elle et **la boucle n'a
plus de moteur événementiel tant qu'aucune autre n'est ouverte** — c'est le
filet toutes les 6 h qui reprend la main, et c'est normal, pas une panne. Le
premier geste d'une nouvelle tranche est donc d'ouvrir une PR depuis une
branche neuve partant de `main`, puis de s'y abonner : sans ça, « verte »
n'a rien à qualifier.

Ordre de priorité à chaque réveil, sans exception :

1. **CI rouge, ou commentaire de revue en attente → c'est ça le travail.**
   Rien d'autre ne commence tant que la PR n'est pas revenue au vert. Une
   régression trouvée par la CI passe avant n'importe quel item de la file :
   elle est déjà payée, il ne reste qu'à la lire.
2. **PR verte et file non vide** → l'item non clos le plus haut, un geste, un
   commit, un push.
3. **Sinon** → arrêt, avec la raison au journal.

**Deux réserves qui ont valeur de règle.** Les webhooks ne livrent pas tout —
succès de CI, nouveaux pushes et passages en conflit arrivent en retard ou pas
du tout. Donc : *vérifier l'état réel de la PR plutôt que le supposer*, et un
**filet horaire toutes les 6 h** existe pour le cas où aucun événement
n'arrive. Ce filet n'est pas le moteur ; s'il fait le travail, c'est qu'un
événement s'est perdu.

**Et le vert local ne vaut pas le vert de la CI.** La CI exécute la suite sur
**3.11, 3.12 et 3.13**, plus le backend, le frontend, la dérive des types
OpenAPI, la construction Docker et le paquet. Un geste vert ici peut être
rouge là-bas — c'est précisément à ça que sert la PR, et c'est pour ça que
« verte » et non « la suite passe chez moi » est la condition de sortie.

---

## Règles permanentes

1. **Un geste, un commit vert.** La suite de la bibliothèque passe avant
   chaque commit (`pytest` dans `packages/saknussemm`), plus `ruff check`,
   `ruff format --check` et `python -m mypy --strict src/saknussemm` avec le
   pin de `[typecheck]` — le `mypy` du conteneur peut être d'une autre version
   et ne pas voir pydantic ; 55 faux positifs en sont sortis une fois.
2. **En cas de doute, s'arrêter et écrire la question.** Ne jamais trancher un
   arbitrage de produit. Les décisions déjà prises sont dans `docs/PLAN.md`,
   section « Décisions déléguées » ; tout ce qui n'y est pas et qui engage la
   surface publique, un coût, une licence ou une dépendance externe est un
   arrêt.
3. **Ne rien attaquer qui exige clés, réseau, argent ou humain.** Ces items
   sont listés plus bas sous « Passe la main au CLI » et ne sont pas dans la
   file. Les rencontrer est une condition d'arrêt, pas un problème à
   contourner.
4. **`P5` tient partout** : aucun cas de test supprimé, noms et docstrings
   conservés lors d'un déplacement, et la preuve est le diff des noms
   collectés par `pytest --collect-only`.
5. **Ce que la vague RM s'interdit reste interdit** : `core/pairing.py`,
   `core/hyphenation.py`, `formats/alto/rewriter.py` ne sont pas découpés.
6. **Avant d'attaquer un item, vérifier dans le CODE qu'il est encore
   ouvert.** Un item peut être clos dans le code et resté ouvert dans le plan
   — `S3b` l'était, et la file en a hérité. Le plan décrit l'intention ; les
   tests décrivent l'état.
7. **Choisir un corpus de mesure pour sa TAILLE est un biais, pas une
   commodité.** Le 2026-08-20, toutes les mesures sur modèles locaux ont été
   faites sur une page de 72 lignes choisie parce qu'elle finissait vite. Elle
   s'est révélée être du bruit : **41,7 % de lignes lisibles, confiance OCR
   médiane 0,50**, contre 84 % / 0,91 et 93 % / 0,98 pour les pages du corpus
   de référence. Sur une telle page, la bonne réponse d'un correcteur est « ne
   corrige presque rien » — donc aucun taux de correction mesuré là n'est
   comparable à quoi que ce soit. Vérifier la représentativité AVANT de
   mesurer, pas après avoir tiré des conclusions.
8. **Un résultat qui va dans le sens espéré demande plus de vérification
   qu'un résultat décevant, pas moins.** Même jour : un producteur en texte
   brut a rendu « zéro retentative, zéro repli, deux fois plus de
   corrections, quatorze fois plus rapide ». Les corrections étaient en
   réalité le délimiteur du format qui **fuyait dans le texte** — `'I'`
   devenu `'I |'`. Le tableau était flatteur, la sortie était une régression,
   et seule la lecture des lignes l'a montré. Lire le TEXTE, jamais
   seulement les compteurs.
9. **Vérifier qu'un corpus de mesure porte bien l'ENTRÉE, pas la sortie
   attendue.** Le 2026-08-20, la sonde vision sur `corpus/37-GT-BNL` a
   donné au modèle le texte du XML — qui est la **vérité terrain**, pas
   l'OCR. L'OCR dégradé vit dans `ocr_spa_sidecar.json`, que les campagnes
   rejouent. Le modèle recevait donc la réponse et devait la « corriger ».
   Lancé tel quel sur 522 lignes, ça aurait produit un CER excellent et un
   énoncé faux — « un 3B local égale un modèle distant ». C'est le seul
   piège de harnais de la journée qui aurait été **flatteur** : les trois
   autres donnaient des résultats visiblement décevants, donc questionnés.
   Ce qui l'a attrapé n'est pas le résultat mais une **incohérence de
   contrôle** — des lignes filtrées comme « abîmées » se sont révélées
   identiques à la référence.
10. **Sur une chaîne vision, REGARDER le crop avant de juger le modèle.**
    Le 2026-08-20, `churro-3B` a été mesuré à CER 0,1825 — 76 % pire que de
    ne rien faire — et le chiffre ne disait rien de lui : l'ALTO du corpus
    BNL est en **dixièmes de millimètre**, son étendue faisant 674×845 pour
    une image de 796×998, soit exactement `300/254`. Sans `ImageTransform`,
    chaque crop était décalé et rétréci de **18 %**, de plus en plus loin du
    texte en descendant la page — donc plausible, jamais vide. Le modèle
    était jugé sur des régions qui ne contenaient pas la ligne annoncée.
    `run_vision.py` documente le facteur en clair ; il n'avait pas été lu.
    **Et c'est la deuxième fois** : le journal du 2026-08-06 porte déjà
    « ImageAsset construit sans transform — échelle 0,1754, crops hors
    cadre ». Écrire le crop sur disque et le regarder coûte trente secondes
    et aurait épargné deux mesures complètes.
11. **Une CI vide n'est pas une CI verte.** Merger demande de compter les
   vérifications **réussies**, jamais de constater l'absence d'échec. Payé le
   2026-08-19 : la condition automatique était « zéro en attente et zéro en
   échec », elle a lu une liste **vide** — un commit venait d'être poussé et
   les vérifications n'étaient pas encore enregistrées — et a mergé `#152`
   sans qu'aucune n'ait tourné. `main` s'est trouvée verte par chance, pas par
   méthode. La condition correcte compte les succès et exige qu'ils soient au
   nombre attendu.

### Conditions d'arrêt

La boucle s'arrête — et écrit pourquoi ici — dès que l'une est vraie :

- la CI est rouge pour une cause qu'on ne sait pas lire après une tentative ;
- la suite locale est rouge et la cause n'est pas le geste en cours ;
- l'item suivant exige clés, réseau, budget, licence ou revue humaine ;
- l'item suivant demande un arbitrage absent de « Décisions déléguées » ;
- deux réveils consécutifs sans progrès mesurable ;
- la file est vide.

---

## La file

**Réécrite le 2026-08-16.** Les cinq items précédents sont clos ou déplacés :
`S3b` et `RM-08` étaient déjà faits, `T1`/`T3` change de borne (décision n°8),
`S4` reste de la documentation pure, et `M1` part au banc avec le reste de la
mesure. La file suit désormais les phases des décisions du 2026-08-16.

Dans l'ordre. Un item se ferme quand son « fini quand » est vérifiable par
quelqu'un qui n'a pas suivi le travail.

### ~~Phases 0 à 2~~ — **faites le 2026-08-16**

Le socle d'autonomie, la scission en trois dépôts, et le gros de « la
bibliothèque devient publiable ». Ce dépôt ne contient plus que la
bibliothèque : la démo est dans `saknussemm-demo`, les corpus, les
campagnes, leur outillage et le scorer QE sont au banc. La CI est passée de
13 jobs à 5 et exécute désormais l'extra `[vision]`, que rien ne lançait.

Le projet a aussi été renommé deux fois le même jour — `corrigenda` →
`lidenbrock` → `saknussemm` — et l'arbre a été aplati : la bibliothèque
EST le dépôt.

### 1. Phase 3 — `0.10.0rc1`, puis `0.10.0`

**Bloqué sur le mainteneur, et sur lui seul.** Deux configurations
externes que personne d'autre ne peut faire : déclarer le *trusted
publisher* sur pypi.org **et** test.pypi.org — projet `saknussemm`, dépôt
`saknussemm`, workflow `publish-saknussemm.yml` — et créer les
environments GitHub `testpypi` et `pypi`. Sans eux, le premier dispatch
échoue à l'échange OIDC.

Ce qui reste ici : couper une section de release dans un `CHANGELOG` qui
porte 1316 lignes sous `[Unreleased]`. Le geste demande de connaître le
numéro, donc il suit la décision de publier plutôt que de la précéder.

### 2. `T1`/`T3` — la liste des promesses

**La liste existe** : `docs/promises.md`, relevé du 2026-08-16. La borne
n'est plus un compteur mais une couverture, et l'item se ferme quand la
liste est couverte.

Fermées le jour même : quatre invariants d'EditScript dont les gardes
existaient et que rien n'atteignait, plus deux promesses étendues à PAGE.
Restent des « partielles », et trois « aucune » qui demandent une décision
— figer l'union `EditOp`, faire converger les deux voies d'édition sur un
même verdict, comparer les rôles de césure entre formats.

**Un trou d'implémentation attend un arbitrage** : `E5b`, la garde du
mot-frontière, qui n'existe pas. Sa forme est une décision de conception,
écrite dans `docs/promises.md`.

### 3. Phase 4 — l'intégration au banc

**FAITE le 2026-08-21** — les cinq briques, `cinoc` #87 à #95 :

| brique | ce qu'elle a livré |
|---|---|
| étape `LAYOUT → LAYOUT` + source ALTO | un ALTO entre dans le banc **sans être aplati** ; la chaîne tourne par le vrai exécuteur |
| vision pour l'adapter Ollama | l'adapter était `text_only` **en dur** alors que le planificateur lui passait déjà un `role` : « OCR → VLM » avec un modèle local produisait un run texte, **en silence** |
| runs répétés | `--repeat N` et une **fourchette** par métrique — `M2` l'exigeait, rien ne le fournissait |
| métriques d'identité de ligne | l'appariement était une devinette : elle diverge sur **57 lignes de 522** et porte le CER par ligne de 0,1188 à 0,1879 |
| dé-césure | profil de normalisation, **pas** option du projecteur : les profils s'appliquent des deux côtés, donc la symétrie est acquise par construction |

**Trois briques ont changé de justification une fois mesurées**, et c'est le
gain principal de les avoir chiffrées avant de les écrire :

- la **dé-césure** ne fait pas baisser l'erreur — elle la fait légèrement
  *monter* (0,1119 → 0,1133). Son intérêt est l'asymétrie : un correcteur qui
  recolle correctement un mot coupé est **pénalisé pour avoir bien fait**
  (0,1179). Construite sans mesure, elle aurait été livrée avec la mauvaise
  justification, et personne n'aurait su quand l'activer ;
- les **métriques d'identité** : j'avais écrit que la devinette « décale tout
  d'un cran ». Faux. Le test censé le prouver ne reproduisait pas le
  phénomène ; vérification faite, l'effet est un décalage des **blocs
  d'opcodes** qui fait déclarer non appariées des lignes voisines quasi
  parfaites — 51 sur-notées contre 6 sous-notées, dont 14 à CER 1,0 ;
- la **vision Ollama** n'était pas une fonctionnalité manquante mais un
  **silence** : le mode existait dans l'interface, le planificateur le
  déclarait, l'adapter l'ignorait, et rien ne le signalait.

**Deux décisions de conception ont été tranchées par la mesure**, contre ce
que l'analyse recommandait :

- **pas de type `CORRECTED_LAYOUT`.** Le module émet `LAYOUT` **et**
  `CORRECTED_TEXT` ; le bilan de correction de `cinoc` fonctionne alors
  **inchangé** — vérifié en appelant le vrai `correction_analysis`. Ajouter
  un type d'artefact sans consommateur aurait été la feature spéculative que
  le `CLAUDE.md` de `cinoc` interdit ;
- **rien à changer à `_CANDIDATE_PRECEDENCE`.** J'avais lu la liste sans
  lire la suite de la fonction : les types absents y sont ajoutés quand
  même, après les autres.

**Ce que la brique 1 a trouvé en chemin, et qui vaut plus qu'elle** :
`cinoc` ne lisait ni les `<SP>` ni les `<HYP>` d'un ALTO. Sur le corpus
BnF, **118 lignes sur 566 portaient un texte faux et 205 perdaient leur
rôle de césure**. Le même défaut existait à l'écriture — `write_alto`
n'émettait aucun `<SP>` — si bien que les deux erreurs **s'annulaient** et
que l'aller-retour se comparait égal à lui-même. Corriger le parser seul a
fait tomber 9 tests, qui mesuraient cette symétrie et non la fidélité du
format.

Sur `corpus/37-GT-BNL`, zéro perte avant comme après : ce corpus n'a ni
`<HYP>` ni `SUBS_TYPE`. Un seul corpus ne prouvait donc rien — et c'était
celui qui servait de référence.

**Ce qui reste ouvert et demande un arbitrage** : montrer *pourquoi* une
ligne n'a pas été corrigée. Les motifs de refus sont calculés puis jetés,
faute d'un canal pour les porter jusqu'au rapport. Le seul canal de `cinoc`
est un artefact typé, donc un ajout à `ArtifactType` — de la surface
publique.

Le corpus et les campagnes sont déjà là-bas. Le scorer QE aussi, en dépôt
d'attente — l'intégrer demande un arbitrage, un scorer n'étant pas une
brique de pipeline.

### 4. Phase 5 — la mesure, puis Phase 6 — `review_required`

Inchangées. `M5` est fermé (trois pages Gallica épinglées bloquent
désormais un merge), `M4` est retiré sur mesure, et `M3` ne coûte plus rien
— Ollama et ses modèles vision sont déjà sur la machine.

## Passe la main au CLI

Ces items ne sont pas dans la file et ne doivent pas être tentés ici. Ils sont
listés pour que la raison soit lisible, pas pour être contournés.

| item | ce qu'il exige |
|---|---|
| `M2` | la moitié Mistral coûte de l'argent : plafond de dépense, donc arbitrage |
| `M5`, `M6` | **quels** corpus télécharger — un choix de projet, pas un critère technique. Les licences, elles, sont tranchées (`Gate 0`) |
| `G1`-`G3` | `review_required` : décider *quelles règles* envoient en revue — conception |
| `P1`, `P2` | deux configurations externes que seul le mainteneur peut faire : déclarer le *trusted publisher* sur pypi.org **et** test.pypi.org, et créer les environments GitHub `testpypi` / `pypi`. Puis dispatcher le workflow |
| `P3` | revue humaine externe |

**Ce qui a quitté ce tableau le 2026-08-16** : `M3` ne demande plus ni clé ni
budget (modèles locaux, décision n°10) ; `M4` est réfuté et doit être réécrit
avant d'être planifié ; `M7` est largement acquis par le déménagement au banc.

**Rappel qui vaut contrainte** : aucune revendication chiffrée ne sort du
dépôt sans `M2` + `M3`. Vérifié le 2026-08-11 — les deux `README` ne portent
aucun chiffre, et le rester est une contrainte sur toute note de version.

---

## Journal

Une ligne par réveil : date, item, résultat, ou la raison de l'arrêt.

- 2026-08-11 — file écrite, Routine armée.
- 2026-08-11 — `S3b` : mesure faite, **cible renversée**, garde posée
  (`test_public_surface_is_the_closure.py`, 4 cas). **Arrêt** : l'item demande
  un arbitrage absent des « Décisions déléguées » — la porte avancée est-elle
  publique ?
- 2026-08-11 — arbitrage **tranché** (décision n°5) : la porte est publique.
  `S3b` reste en tête de file, son contenu est maintenant exécutable sans
  décision : ajouter 9, rétrograder 4, reformuler `V5`, mettre `_LAZY`,
  `docs/versioning.md` et le `CHANGELOG` en accord.
- 2026-08-12 — **PR #71 ouverte**, 23 commits, **CI verte 17/17** (dont la
  suite sur 3.11/3.12/3.13, le backend, la dérive OpenAPI et le paquet). La
  boucle est recâblée sur les événements de la PR ; le cron passe de horaire à
  filet toutes les 6 h.
- 2026-08-12 (filet) — PR verte, 0 fil de revue, `mergeable_state: clean`.
  `S3b` attaqué, **puis annulé en cours de geste** : la lecture de
  `test_public_api_snapshot.py` a montré qu'il était **déjà fait** depuis le
  2026-08-01 et que les « 9 trous » sont un troisième seam laissé ouvert par
  écrit. Surface restaurée à 66, décision n°5 annulée, mesure du plan
  rétractée, règle n°6 ajoutée. Reste acquis : la garde qui recalcule les deux
  clôtures. **Prochain item : `RM-08`.**
- 2026-08-12 (filet) — PR verte 17/17, 0 fil de revue. `RM-08` **clos par la
  mesure, sans toucher au code** : constat périmé, les deux projections
  partagent la dérivation et divergent pour une raison écrite. Test de
  divergence ajouté (3 cas, sensibilité vérifiée en simulant la fusion). Le
  cliquet des internes a attrapé le test lui-même — symbole nommé. **Deux
  items de suite se sont révélés déjà clos ; c'est un motif, pas une
  coïncidence : le plan décrit l'intention, le code décrit l'état.**
  Prochain item : `T1`/`T3`.
- 2026-08-13 (filet) — PR verte 17/17, 0 fil de revue. `T1`/`T3` : **2
  propriétés ajoutées**, chacune vérifiée par mutation délibérée. (1) l'ordre
  des fichiers d'entrée ne change rien de ce que le run rend — la première
  version ne détectait pas `F4` et a été élargie au script d'édition ; (2) la
  somme des pertes par ligne reproduit l'agrégat — une promesse **écrite dans
  le contrat et vérifiée nulle part**, la famille `R1`. Aucun défaut trouvé.
  Prochain réveil : suite de `T1`/`T3` (4 propriétés avant la borne).
- 2026-08-13 (filet) — PR #72 verte 17/17, `mergeable_state: clean`, 0 fil
  de revue. `T1`/`T3` : **1 propriété ajoutée** — ce que le rapport dit du
  fichier, relu dans le fichier. Le réécriveur documente son raccourci (les
  textes de sortie sont lus sur l'arbre, « without a second full parse of
  the output ») ; rien ne relisait les octets réellement rendus. **Deuxième
  angle mort de la suite entière en deux tours** : `.replace(b"\xc2\xa0",
  b" ")` sur `etree.tostring`, une expression, laisse les **1407** autres
  tests au vert pendant que chaque fichier livré perd son espace insécable.
  Compteur à 5/6, et la question de ce que « trouver un défaut » veut dire
  est posée plus haut plutôt que tranchée. Prochain réveil : la 6ᵉ propriété
  déclenche la borne — donc `S4` (documentation seule) si le mainteneur n'a
  pas répondu.
- 2026-08-13 (filet) — aucune PR ouverte, donc aucun événement : le filet
  fait exactement ce pour quoi il existe. Branche repartie de `main`, **PR
  #72 ouverte et abonnée**, puis `T1`/`T3` : **2 propriétés ajoutées**. (1)
  `T3` — rejouer le script d'édition rendu doit reproduire le fichier rendu,
  une promesse écrite dans la docstring de `_build_final_edit_script` et
  comparée nulle part ; (2) `T1` — une seconde passe sur la sortie ne bouge
  rien sauf le `postProcessingStep` qu'elle ajoute. **La seconde a trouvé un
  angle mort de la suite entière** : réutiliser le pas de provenance au lieu
  de l'ajouter laisse les 1404 autres tests au vert. Aucun défaut dans le
  code. Compteur à 4/6. Prochain réveil : `T1`/`T3` (2 avant la borne), puis
  `S4` en documentation seule.
- 2026-08-13 — **PR #71 mergée** dans `main` (27 commits). Avant merge, deux
  décisions déléguées ont été trouvées **vidées de leur contenu** par la
  découverte que `S3b` était déjà fait : « pas d'extension de surface tant que
  `S3b` n'a pas coupé » ne contraignait plus rien, et « `S3b` avant tout tag »
  était satisfait avant d'être écrit. Reformulées, pas laissées. **Prochain
  geste : nouvelle branche depuis `main`, nouvelle PR, s'y abonner.**
- 2026-08-14 — **PR #72 mergée**, puis #74 (`T3` : la même phrase posée au
  réécriveur PAGE) et #75 (les deux cliquets de décision ne voyaient qu'une
  orthographe de l'écriture). Ces trois tours **n'ont pas été journalisés à
  l'époque** : la boucle a mergé sans repasser ici, ce que la règle du dépôt
  interdit. Réparé le 2026-08-16, à la lecture.
- 2026-08-16 — **PR #76 mergée** : la campagne `M2`, cinq runs. Non journalisée
  non plus, et c'est la plus coûteuse des trois omissions, parce que la
  campagne **invalide ses propres chiffres** : le correctif de banc `2e0b7bc`
  arrive après les cinq runs. La ligne `M2` du plan décrivait encore la
  campagne comme à faire, avec les chiffres de juillet. Le motif est celui que
  `D*` avait fermé et qui revient dès qu'on cesse de le surveiller : **le plan
  décrit l'intention, le code décrit l'état, et personne ne les rapproche.**
- 2026-08-16 — revue d'état complète demandée par le mainteneur, puis
  cartographie de `cinoc` par trois agents. Deux constats qui ne venaient
  d'aucun document : `cinoc` **est** le banc que ce plan s'apprêtait à
  reconstruire (1667 tests, 96 % de couverture, 24 métriques, Space en ligne),
  et il ne mentionne `saknussemm` **nulle part**. Les deux projets sont
  complémentaires sur la ligne exacte où chacun est aveugle : `cinoc` compare
  des pages aplaties et ne lit jamais `Line.id` ; `saknussemm` garantit la
  ligne et ne sait mesurer qu'un CER, dans un script faussé. Dix décisions en
  ont découlé (`docs/PLAN.md`), et cette file est réécrite autour.
- 2026-08-16 — **le renommage.** `corrigenda` devient `saknussemm` : 1979
  occurrences, 312 fichiers, quatre chemins, PR #80. Les quatre empreintes
  de parité d'octets ont bougé et ont été **classées avant d'être
  re-figées**, en rendant la même fixture avec le code d'avant dans un
  worktree : trois lignes de diff, toutes dans le tampon de provenance,
  10280 octets des deux côtés — les deux noms font la même longueur. Zéro
  dérive de ligne. `docs/history/` garde l'ancien nom, et une note en tête
  dit pourquoi : ces documents ont été écrits quand c'était le nom, et
  l'historique git le portera de toute façon. L'ordre des imports du
  backend a cassé — trouvé par la CI, pas en local, parce que la règle
  n'était activée que d'un côté. **Même leçon que l'extra `[test]` deux PR
  plus tôt : ce qui n'est déclaré qu'à un endroit finit par diverger.**
- 2026-08-16 — **la scission.** `saknussemm-demo` créé, public, 282 commits
  filtrés, 467 tests. Puis PR #81 : 148 fichiers retirés d'ici. Deux
  oublis de ma part rattrapés par un rouge plutôt que par un silence —
  l'installation depuis git échouait (`Multiple top-level packages
  discovered in a flat-layout`, d'où `#subdirectory=`), et un **second**
  `Dockerfile` copiait encore la bibliothèque. Le premier a transformé
  l'aplatissement de l'arbre en nécessité technique et non plus en
  préférence.
- 2026-08-16 — **trouvé en cherchant autre chose.** En cherchant un corpus
  multi-pages pour `M1`, la sonde Gallica a buté sur des ALTO BnF refusés à
  la porte : namespace d'éditeur (`bibnum.bnf.fr/ns/alto_prod`), et
  déclaration d'encodage fausse (ISO-8859-1 annoncé, UTF-8 réel). Les deux
  fermés, PR #79. Le parseur et le réécriveur étaient agnostiques depuis
  toujours — **la porte était le seul endroit marqué du dépôt.** `M1` reste
  ouvert : le corpus n'a pas été trouvé, le défaut si.
- 2026-08-16 (suite) — **la scission est finie, et onze dettes avec.**
  `saknussemm` ne contient plus que la bibliothèque : 347 fichiers suivis,
  la démo dans son dépôt, les corpus et les campagnes au banc, le scorer QE
  déposé là-bas aussi. Réglé au passage : la porte marquée sur un namespace
  d'éditeur, une déclaration d'encodage crue sur parole, l'environnement de
  test déclaré dans un workflow, la garde de publication égarée dans le
  backend, deux angles morts de la garde de profondeur, une exclusion de
  couverture justifiée par une raison devenue fausse, quatre sauts
  silencieux, le double parsing (−23 % au chargement), le corpus externe qui
  ne bloquait aucun merge (`V7` tenu), `.cache/` non ignoré, cinq références
  pourries dans la démo, et une garde de licence restée orpheline.

  **Le motif, énoncé une fois pour qu'on le reconnaisse plus vite** :
  presque chacune de ces dettes était une garde plus étroite que ce qu'elle
  prétendait couvrir, ou une raison écrite une fois et jamais revérifiée.
  Élargir la garde a trouvé, chaque fois, plus que la lecture : deux sauts
  silencieux lus contre quatre trouvés ; un `Dockerfile` vu contre deux
  existants ; deux portes lxml surveillées contre quatre réelles.

  **Et trois fois dans la journée, le vert local n'a pas valu le vert de la
  CI** : PyYAML présent d'un côté seulement, tri d'imports activé d'un seul
  côté, `.cache/` présent en local et absent là-bas. La vérification se fait
  désormais dans la condition de la CI, pas dans la sienne.

  Reste ici : retirer l'extra `[qe]` quand le dépôt du banc l'a accepté, et
  couper une section de release dans un `CHANGELOG` qui porte 1316 lignes
  sous `[Unreleased]`. Reste au mainteneur, et ça bloque la `0.10.0rc1` :
  les secrets HF de la démo, et le *trusted publisher* PyPI.
- 2026-08-16 (fin de journée) — **le relevé des promesses a expliqué un
  motif que je prenais pour de la négligence.** Il disait « PAGE est le
  format sous-gardé », six promesses partielles pour cette seule raison. En
  cherchant pourquoi, j'ai trouvé que le harnais de tests importait le
  parseur ALTO directement — et que **63 modules de tests font pareil**,
  six seulement passant par le loader. Sur un fichier PAGE valide, chacun
  obtenait un manifeste de 0 page et 0 ligne, sans erreur. Toute propriété
  qu'on y aurait affirmée passait au vert sur un run vide.

  Le plus instructif : **un test épinglait cette mauvaise lecture comme
  comportement attendu**, avec un commentaire disant « the silent mis-read,
  still true ». Le danger était connu, documenté dans le docstring du
  loader, et testé — traité comme un fait de la vie qu'on contourne plutôt
  que comme un défaut qu'on retire.

  Fermé à la source : le parseur ALTO refuse désormais ce qui n'est pas de
  l'ALTO, ce qui corrige les 63 sites d'un coup sans en éditer un seul. Et
  le harnais refuse un manifeste sans lignes, quelle qu'en soit la cause —
  c'est la partie qui survit au correctif.

  **La règle que j'en tire, pour les prochains tours** : quand une famille
  entière de propriétés est faible sur un axe, chercher l'outil avant de
  chercher la négligence. Personne n'a de raison de soupçonner un test vert.

- 2026-08-18 — **le premier vrai run**, et il a corrigé plus d'affirmations
  que tout l'audit qui l'a précédé. 24 592 lignes de presse Gallica par
  `mistral-small`, un job à la fois : 66 % corrigées, 1,02 $, **quatre pages
  perdues**. Le relevé complet est en section `B` de `docs/PLAN.md`.

  **Deux défauts que rien d'autre n'aurait trouvés, corrigés** : un invisible
  retiré exprès par l'écrivain tuait deux pages sur quinze, parce que
  l'échelle de fidélité n'avait aucun niveau pour un retrait déclaré (#125) ;
  et un étranglement était rapporté comme une incapacité du modèle, la
  distinction existant déjà dans la classification mais cessant de voyager
  jusqu'au message (#128).

  **Un troisième reproduit et laissé OUVERT** (#126) : le chemin lent soude
  la marque de coupure au mot qui la précède. Le correctif touche la
  reconstruction géométrique, et écrire de la mauvaise géométrie dans un
  fichier livré est pire que l'espace perdue. Son test d'acceptation est
  écrit — il n'y a qu'à inverser son assertion.

  **La démo est devenue un poste de revue humaine** (`saknussemm-demo` #4),
  mergée et déployée. Elle porte le verdict par ligne, la coloration par
  famille, le filtre qui estompe, et surtout **de quoi trancher et annoter** :
  le verdict `transcribed` enregistre ce qu'un lecteur lit sur le scan, et
  s'accumule en vérité terrain. Vérifié de bout en bout sur un vrai run, pas
  seulement par ses tests.

  Elle ne pouvait pas exécuter la moitié vision de la bibliothèque : aucun
  fournisseur n'implémentait `complete_structured_multimodal`, et l'extra
  `[vision]` n'était installé nulle part. Ce n'était pas une régression —
  cette méthode n'a jamais existé dans son historique. La capacité avait vécu
  23 jours comme outil à la racine du dépôt de la bibliothèque et est partie
  avec l'archive du banc, emportée par un défaut prouvé chez sa voisine.

  **Quatre erreurs de méthode, consignées parce qu'elles se reproduiront.**
  Mesurer une garde anti-hallucination avec un producteur qui ne peut pas
  halluciner. Saturer son propre quota et l'attribuer au modèle — 67 % de
  corrections seul contre 37 % à trois jobs, sur la même page. Réimplémenter
  au lieu de lire les dépôts consommateurs, dont un commentaire citait déjà
  l'erreur que j'ai redécouverte. Et comparer un bras texte à un bras vision —
  reproche juste, mais la raison que j'en donnais était **fausse** (corrigée
  le 2026-08-20) : la ligne « text » de la campagne de référence n'est pas un
  LLM mais trois substitutions déterministes, sur un corpus où aucune ne
  s'applique.

  **Le mode « une page, un appel » est chiffré** : 28 appels au lieu de 2 000,
  0,39 M de tokens au lieu de 5,49 M. L'enveloppe JSON par ligne pèse 7,9 fois
  le texte qu'elle transporte, chaque ligne étant transmise trois fois via
  `prev_text` / `ocr_text` / `next_text`. C'est un producteur, donc aucun
  changement du cœur ; le travail neuf est l'aligneur, et la garde qui attrape
  son mode de défaillance existe déjà.

  **Arrêt** : ce qui reste demande le mainteneur. Le *trusted publisher* sur
  pypi.org et test.pypi.org plus les environnements GitHub — le workflow est
  scindé et stable depuis #119, donc c'est le bon moment. Et l'arbitrage sur
  l'aligneur.

- 2026-08-19 — **le plan `C` écrit, puis exécuté en entier.** Sept PR mergées
  ici, une à la démo. Le plan lui-même est né d'une **contre-analyse** exigée
  par le mainteneur : sept constats sur dix de la première version ont bougé,
  et la section les nomme plutôt que de les effacer.

  **`C1` — la marque de coupure garde son espace** (#131, ferme #126). Une
  ligne Gallica réelle décidée `'…et d -'` était écrite `'…et d-'` : les mots
  divergent, donc `ProjectionError`, donc **le document entier perdu**. La
  raison écrite pour laquelle le défaut est resté ouvert deux jours — « le
  correctif touche la géométrie » — est fausse deux fois : la géométrie est
  gratuite dès qu'on taille l'espace DANS la fente réservée au `HYP`, et le
  vrai obstacle était une perte d'information en amont que personne n'avait
  nommée. Et la population n'avait jamais été mesurée : 29 lignes sur 24 694,
  mais **10 fichiers sur 35**, tous de deux fascicules — une signature de
  producteur, pas un aléa.

  **`C2` — le coût de la césure publié** (#132). Deuxième cause de refus du
  run du 18 août, 2 271 lignes, et rien ne le disait. Le chiffre était déjà
  dérivable ; ce qui manquait était la phrase, et la garde qui l'empêche de
  dériver.

  **`C3` — le rayon d'action, en deux temps** (#133, #134). D'abord finir la
  boucle de réécriture : trois fichiers fautifs coûtaient trois runs facturés
  pour être découverts, maintenant un seul. Puis l'arbitrage, **remonté au
  mainteneur** : un fichier divergent est désormais **retenu** et non fatal
  au run. Ma première recommandation était de garder le refus total ; le
  mainteneur a demandé pourquoi, et trois de mes quatre arguments ne
  tenaient pas. Le quatrième — un mot coupé à cheval sur deux fichiers livré
  à moitié — a été **mesuré** : **0 sur 1 583** unités de césure, détecteur
  vérifié contre un positif fabriqué. Recommandation inversée.

  **La démo aurait menti** (`saknussemm-demo` #5). Elle a son propre
  écrivain, donc elle contourne par conception le refus de `write()` : elle
  aurait écrit 299 pages sur 300 en rapportant un succès. Et le défaut le
  plus dangereux était côté interface — un état terminal absent de la liste
  du flux SSE n'empêche pas d'afficher une étiquette, **il empêche le flux de
  se fermer**.

  **`C4` — le mode page, en quatre pièces** (#135 à #138). L'aligneur ne
  matérialise plus ses matrices : de ~2,4 Go et un échec mémoire à **4,48 s
  et 31 Mo** sur la page réelle la plus lourde, équivalence prouvée contre
  l'algorithme d'origine gardé comme oracle. Puis l'alignement ligne-à-ligne
  (Jaccard, aussi discriminant que Levenshtein et 13× moins cher, 0,05 s la
  page), le contrat et le producteur, et les deux modes nommés dans le
  README.

  **Deux revendications à moi corrigées par la mesure.** « La bande donne la
  garde gratuitement » : non — `band_exhausted` dit *où la recherche est
  allée*, pas si la lecture est bonne, et une suppression massive ne le
  déclenche pas du tout. Et la première version de `page_alignment` laissait
  la ligne avalée par une fusion sans cible — test vert — pendant que
  l'AUTRE ligne recevait les mots de sa voisine. Vu seulement en écrivant un
  cas jouet qui a cassé pour la mauvaise raison. La garde qui a suivi est
  mesurée : une correction déplace le compte de jetons de **±1, 100 % du
  temps** sur 8 859 paires ; une fusion de **+6 à +14**.

  **Les garde-fous du dépôt ont refusé sept fois** — longueurs de fonction,
  nombre d'arguments, étiquettes de ticket, pin du JSON du rapport, protocole
  `JobStore`, dérivation dupliquée. À chaque fois ils avaient raison : le
  code a été déplacé, jamais le cran desserré.

  **Ce que le mode page n'a pas** : un run réel. Tout est mesuré sur des
  lignes réelles avec des corrections **simulées**, et une simulation ne dira
  jamais ce qu'un modèle fait quand on lui demande mille lignes d'un coup.

- 2026-08-19 (suite) — **item 2 de la file : `docs/promises.md` vidé de tout
  ce qui ne demande pas d'arbitrage.** Sept promesses fermées, sept PR.
  Zéro correctif de production sauf un ; le reste est du test, et le motif
  qui revient est que **le test écrit d'abord ne prouvait pas ce qu'il
  annonçait**.

  **Le point fixe étendu à PAGE.** Le dépouillement de provenance a dû
  devenir format-conscient : ALTO écrit un élément par passe, PAGE 2013 —
  le schéma de toutes les fixtures livrées — **ajoute une ligne** à un
  unique `Metadata/Comments`. Un compteur d'éléments lisait ça « zéro
  passe », d'où deux échecs pour une cause. Limite écrite dans le test : une
  transformation **déterministe** appliquée aux deux passes est un point
  fixe par construction, donc cette propriété voit une asymétrie
  écriture/lecture, jamais un rewriter stablement faux.

  **`E4a`, la borne par op.** Le test à deux ops évident ne prouve rien : si
  chaque op respecte `len ≤ r × span`, leur somme aussi, donc une borne
  cumulative accepte exactement les mêmes scripts. Écrit ainsi d'abord, et la
  mutation cumulative l'a laissé vert. Le cas discriminant va dans l'autre
  sens — une op qui rétrécit un long span paie pour une op gloutonne.

  **`E1`, et la clause était inatteignable.** `attempt.py` passait toutes les
  lignes du chunk comme cibles, donc « hors ensemble » n'était vrai que là où
  « inconnue » l'était déjà. Elle passe les vraies cibles maintenant, et une
  édition de contexte est **refusée** (`e1_context_line`) au lieu d'être
  jetée en aval. Le texte livré ne bouge pas — toute la suite est restée
  verte — seule la trace apparaît, ce que `edit_rejections` permet enfin de
  porter. Seul changement de production du lot.

  **`E6a`, `F2a`.** Un span irréprochable structurellement dont le résultat
  ne ressemble plus à sa ligne : seul l'étage sémantique le voit, et rien ne
  l'exerçait. Et un seul attribut hors liste prouve qu'*il* est jeté, pas que
  la règle est une liste **blanche** — le test asserte la clôture, plus que
  la perte est comptée et que le style suit l'**appariement**, jamais la
  position.

  **La parité d'octets ne portait pas sur les octets.** Le test retirait la
  provenance de l'ARBRE puis re-sérialisait les deux côtés, ce qui normalise
  exactement ce que la promesse vise : `pretty_print=True` le laissait vert.
  Découpé dans les octets, il tombe. Et sa prémisse était trop lâche — « ni
  fast ni slow » laissait `subs_only` revendiquer les lignes.

  **Les compteurs du rapport**, dérivés des octets livrés et non des objets
  qui les ont produits. Trois mutations, chacune tombant sur sa propre
  assertion. Limite énoncée : `fallback_lines` n'est pas vérifiable ainsi.

  **`I2b`, l'union des opérations.** Le test ne décide pas qu'elle ne
  grandira jamais, mais qu'elle ne grandira pas par accident. Deux
  corrections par la mesure : « aucun champ pluriel » gardait une
  orthographe et laissait passer `with_line_id`, et paramétrer les
  propriétés sur la liste figée faisait qu'un nouveau membre ne rencontrait
  jamais les propriétés censées le juger.

  **Arrêt.** Ce qui reste dans `promises.md` demande le mainteneur : `E5b`
  (la garde du mot-frontière n'existe pas, et sa forme est une décision de
  conception) et `E6b` (la voie ligne entière ne passe ni par `E4` ni par
  `E5`, donc les deux gardes ne s'appliquent pas au producteur par défaut).

- 2026-08-19 (fin) — **les deux derniers arbitrages tranchés, sur mesure.**
  `docs/promises.md` ne porte plus aucune ligne « aucune ». Le mainteneur a
  demandé une analyse complète appuyée sur des **runs réels** plutôt que sur
  du raisonnement, ce qui a changé les deux réponses.

  **Un vrai run `mistral-small-latest`** — 3 135 lignes, 1 796 propositions,
  10 fichiers Gallica pour le volet `E5b` et 4 pour le volet `E6b`. Les
  tâches de fond ont été tuées deux fois ; la reprise a été ajoutée au script
  pour ne pas repayer ce qui était déjà collecté.

  **`E5b`.** La règle « seuil de similarité sur le mot-frontière » était la
  candidate évidente, et la mesure l'a réfutée : sur 1 433 lignes
  `PART2`/`BOTH`, ce mot est **remplacé par du méconnaissable 25 % du
  temps**, et ce sont de bonnes corrections — c'est l'endroit le plus dégradé
  de la ligne, souvent réduit à un caractère isolé. Un seuil refuserait
  **23–31 %** des corrections réelles. Refuser le seul **effacement** en
  coûte **0**. Le trou lui-même : **0 occurrence sur 4 752** lignes réelles,
  mais reproductible sur une ligne construite — d'où une assurance sans
  seuil, plutôt qu'une note.

  **`E6b`.** `E4` refuse **0** proposition, `E5` en refuse **205** dont
  **204 étaient déjà refusées** en aval. La parité ne refuse donc pas plus :
  plus tôt, et en nommant pourquoi. **La 205ᵉ a fait affiner `E5`** — une
  espace avant la marque n'est refusée que si la correction l'a
  *introduite*, parce que sur ces 205 elle est héritée de la source 1 fois et
  introduite 0 fois, et cette unique ligne est `#126`, dont juger le seul
  résultat punirait la fidélité. Rejoué : **204 refusées, 0 verdict changé.**

  **Une erreur de mesure attrapée par son propre contrôle.** La première
  passe donnait « `E5` refuse 0 % », et c'était faux : j'appelais
  `_e5_hyphen_ok(texte, rôle)` alors que sa signature est `(rôle, texte)`. Le
  contrôle de sensibilité — vérifier que la mesure *peut* produire autre
  chose que zéro — l'a révélé. Sans lui, un 0 % rassurant serait parti dans
  une recommandation.

- 2026-08-19 (fin) — **les deux derniers arbitrages tranchés, sur mesure.**
  `docs/promises.md` ne porte plus aucune ligne « aucune ». Le mainteneur a
  demandé une analyse complète appuyée sur des **runs réels** plutôt que sur
  du raisonnement, ce qui a changé les deux réponses.

  **Un vrai run `mistral-small-latest`** — 3 135 lignes, 1 796 propositions,
  10 fichiers Gallica pour le volet `E5b` et 4 pour le volet `E6b`. Les
  tâches de fond ont été tuées deux fois ; la reprise a été ajoutée au script
  pour ne pas repayer ce qui était déjà collecté.

  **`E5b`.** La règle « seuil de similarité sur le mot-frontière » était la
  candidate évidente, et la mesure l'a réfutée : sur 1 433 lignes
  `PART2`/`BOTH`, ce mot est **remplacé par du méconnaissable 25 % du
  temps**, et ce sont de bonnes corrections — c'est l'endroit le plus dégradé
  de la ligne, souvent réduit à un caractère isolé. Un seuil refuserait
  **23–31 %** des corrections réelles. Refuser le seul **effacement** en
  coûte **0**. Le trou lui-même : **0 occurrence sur 4 752** lignes réelles,
  mais reproductible sur une ligne construite — d'où une assurance sans
  seuil, plutôt qu'une note.

  **`E6b`.** `E4` refuse **0** proposition, `E5` en refuse **205** dont
  **204 étaient déjà refusées** en aval. La parité ne refuse donc pas plus :
  plus tôt, et en nommant pourquoi. **La 205ᵉ a fait affiner `E5`** — une
  espace avant la marque n'est refusée que si la correction l'a
  *introduite*, parce que sur ces 205 elle est héritée de la source 1 fois et
  introduite 0 fois, et cette unique ligne est `#126`, dont juger le seul
  résultat punirait la fidélité. Rejoué : **204 refusées, 0 verdict changé.**

  **Une erreur de mesure attrapée par son propre contrôle.** La première
  passe donnait « `E5` refuse 0 % », et c'était faux : j'appelais
  `_e5_hyphen_ok(texte, rôle)` alors que sa signature est `(rôle, texte)`. Le
  contrôle de sensibilité — vérifier que la mesure *peut* produire autre
  chose que zéro — l'a révélé. Sans lui, un 0 % rassurant serait parti dans
  une recommandation.

- 2026-08-19 (dernier) — **le mode page contre un vrai fournisseur, la seule
  dette que je pouvais régler seul.** Quatre pages Gallica, 3 135 lignes,
  `mistral-small-latest`. Le résultat contredit ce que `C4` espérait, et
  c'est précisément pourquoi le run existait.

  **L'aligneur tient.** **Zéro** ligne non appariée sur les quatre pages.
  Tout ce que `#135`, `#136` et `#137` ont construit résiste à un vrai
  modèle : la position suffit à retrouver chaque ligne, et la garde de fusion
  n'a eu personne à refuser. La partie que je croyais risquée est celle qui
  n'a pas bougé.

  **Le modèle ne tient pas.** Le taux de lignes qu'il propose de changer est
  **erratique** — 52 %, 2 %, 32 %, 56 % — contre 48 à 72 % en mode apparié
  sur les mêmes pages. Sur `f0002`, **963 propositions sur 986 sont
  identiques à la source** : la page est revenue telle quelle. Pas une loi de
  taille (1 118 lignes ont donné 32 %) mais de la variance, qui prolonge
  l'instabilité de `mistral-small` déjà notée le 18 août.

  **L'économie est réelle**, mesurée sur la même page : 2 appels contre 147,
  0,0051 $ contre 0,0189 $, 77 s contre 234 s. Mais huit fois moins cher ne
  vaut rien si le run corrige cinq fois moins, et combien il corrige n'est
  pas prévisible aujourd'hui.

  **Verdict écrit dans le README et le plan** : mode apparié pour ce dont on
  dépend. Le mode page est complet et sa moitié risquée est prouvée ; ce
  qu'il attend n'est pas du code mais un modèle qui tienne l'attention sur
  mille lignes d'un coup.

  Deux détails de méthode : les tâches de fond se sont fait tuer trois fois,
  d'où une reprise ajoutée aux scripts pour ne pas repayer ce qui était déjà
  collecté ; et le premier lancement a échoué sur un mauvais mot-clé de
  constructeur, ce que seul le lancement révélait.

- 2026-08-20 — **« son mode texte fait 0 improved » était une faute de
  lecture, signalée par le mainteneur.** Il a demandé comment concilier cette
  phrase avec ses propres runs, où le plus petit ministral en texte pur
  améliorait bien quelque chose. Il avait raison et la phrase était fausse.

  La ligne « text » de la campagne BNL n'est pas un LLM : c'est
  `default_french_ocr_rules`, **trois substitutions déterministes** — le `ſ`
  long et les ligatures `ﬁ`/`ﬂ` — passées sur un corpus majoritairement
  **allemand en Fraktur**. Aucune des trois n'y apparaît, donc zéro
  correspondance et zéro changement. C'est le résultat attendu d'une table de
  règles hors de son domaine, et ça ne dit **rien** d'un modèle.

  Ce que le dépôt mesure ailleurs le contredisait déjà : sur Gallica,
  `mistral-small` en texte pur livre **28 à 38 %** des lignes corrigées. Je
  n'avais pas rapproché les deux.

  **Le coût de l'erreur n'est pas la phrase, c'est ce qu'elle a autorisé** :
  écrite deux fois dans le dépôt, elle a servi à justifier de ne pas relancer
  le bras texte. Une conclusion tirée d'une colonne mal lue devient une
  décision de ne pas mesurer — exactement le mécanisme que ce journal existe
  pour attraper.

- 2026-08-21 — **La ligne de base 0,1038 de la campagne BNL est contaminée :
  six lignes reçoivent la vérité terrain en guise d'OCR.**

  Le contrôle imposé par la règle « vérifier la baseline avant de comparer »
  a refusé de tomber juste : le harnais churro mesurait 0,1146 là où la
  campagne annonce 0,1038, sur les **mêmes 522 lignes et la même référence**
  (vérifié : 0 référence divergente).

  L'écart vient de **six lignes où l'OCR dégradé est vide** dans
  `ocr_spa_sidecar.json`. La campagne du 14 août ne les a pas laissées vides :
  elle est retombée sur le texte de l'ALTO, **qui est la vérité terrain**. Les
  six sont identiques à leur référence au caractère près, vérifié une par une.

  **Le mécanisme est écrit noir sur blanc dans le code**, et c'est ce qui
  rend la chose instructive. `apply_ocr_manifest` (`campaigns/tooling/
  vision_benchmark.py`) documente exactement ce piège :

  > *A line the engine returned nothing for keeps its GT text **and is
  > reported by the caller**: an empty reading is a real OCR outcome, but
  > silently treating it as a correct line would flatter every configuration
  > equally.*

  L'auteur avait vu le risque, l'avait nommé, et avait délégué la parade à
  l'appelant. **`run_benchmark` ne compte ni ne rapporte jamais ces lignes.**
  Le contrat de la docstring n'est rempli nulle part, donc l'avertissement
  n'est jamais sorti.

  **Conséquence, et elle diffère selon le harnais.** Côté campagne, les six
  lignes ont la vérité terrain des deux côtés : elles pèsent zéro erreur pour
  la ligne de base *comme* pour chaque arme, et diluent tous les CER vers le
  bas. Côté harnais churro, `ocr_text` est mis à vide explicitement, donc la
  ligne de base y encaisse la perte totale — d'où 0,1146. Aucune des deux
  bases n'est fausse en soi ; ce qui est fautif, c'est de comparer un chiffre
  d'une base à un chiffre de l'autre. Il faut **exclure les six lignes** :
  base propre **516 lignes, OCR 0,1049**.

  C'est la troisième fois que le texte de l'ALTO d'un corpus de vérité
  terrain se fait passer pour de l'OCR. Les deux premières fois, un contrôle
  l'a attrapé. Cette fois, la contamination était **déjà publiée** dans les
  chiffres d'une campagne, et c'est un désaccord de quatrième décimale qui l'a
  révélée. Un contrôle qui « ne tombe pas juste » n'est pas un défaut de
  harnais à contourner : c'est le seul avertissement qu'on recevra.

- 2026-08-21 — **`M3` est fait, et son premier résultat utile est d'avoir
  cassé `M2`.**

  Trois familles de modèles sur la vérité terrain BNL, base propre de 516
  lignes, même chaîne et mêmes gardes pour les trois :

  | | CER | mieux | pire |
  |---|---|---|---|
  | OCR brut | 0,1049 | — | — |
  | `churro-3B` vision | 0,1044 | 62 | 11 |
  | `gemma4:e2b` texte | 0,1021 | 112 | 43 |
  | **`mistral` vision** | **0,0361** | **337** | **10** |

  **Ce que `M3` existait pour séparer est séparé.** Le système ne bouge pas,
  le modèle bouge d'un facteur trois, et aucune des trois familles n'a fait
  casser l'alignement. L'écart de qualité est donc imputable au modèle et non
  au harnais — c'est exactement la question que l'item posait.

  **Ce que le classement seul ferait manquer.** `gemma4:e2b` gagne plus de
  CER que `churro-3B` et **abîme quatre fois plus de lignes** (43 contre 11).
  Pour une bibliothèque dont le principe est « l'application décide », un
  modèle qui touche peu et se trompe rarement vaut mieux qu'un modèle qui
  gagne en moyenne : la moyenne n'est pas la garantie que l'appelant achète.
  Le CER seul est le mauvais critère de sélection ici.

  **Et l'échec de `churro-3B` était le mien.** Avant correction de
  `ImageTransform`, il mesurait 0,1825 — franchement destructeur. Avec les
  bonnes découpes, 0,1044. Le modèle n'avait jamais été en cause ; il lisait
  des bandes d'image décalées de 18 %. La règle du 20 août — *sur une chaîne
  vision, REGARDER le crop avant de juger le modèle* — s'est payée le
  lendemain de son écriture.

- 2026-08-21 — **Deux erreurs symétriques s'annulaient, et c'est le motif du
  jour.**

  `cinoc` ne lisait ni les `<SP>` ni les `<HYP>` d'un ALTO ; son écrivain n'en
  émettait pas non plus. Chaque défaut rendait l'autre invisible : le parser
  rejoignait les mots par des blancs, l'écrivain les écrivait sans blancs, et
  l'aller-retour **se comparait égal à lui-même**. Neuf tests verrouillaient
  cette symétrie en croyant vérifier la fidélité du format.

  C'est la même forme que la contamination trouvée le matin même — un contrat
  de docstring délégué à un appelant qui ne l'a jamais rempli — et que le
  contrôle de ligne de base qui « ne tombait pas juste ». **Trois fois dans la
  journée, le défaut n'était pas dans une valeur mais dans ce qui la
  vérifiait.**

  La leçon opérationnelle : un aller-retour qui compare une sortie à sa propre
  relecture ne prouve rien sur le format. Il faut un point de référence
  **extérieur** — ici, le parser de `saknussemm` lisant le même fichier.

- 2026-08-21 — **J'ai fermé une PR sans le voir.** `gh pr merge --delete-branch`
  a échoué au merge et supprimé la branche quand même, ce qui a fermé la PR.
  J'ai lu « not mergeable » et je suis passé à la suite sans vérifier l'état
  résultant. Le travail était intact sur le distant, mais la pile était cassée.

  **Lire un échec n'est pas lire un état.** C'est la règle 9 sous un autre
  angle : après une opération qui échoue partiellement, vérifier ce qui a
  quand même eu lieu — jamais supposer que l'échec a tout annulé.

- 2026-08-21 — **Mesurer avant de construire a changé trois briques sur cinq.**

  La Phase 4 listait cinq briques par leur *nom*. Trois se sont révélées
  différentes de ce que leur nom laissait croire, et seule la mesure préalable
  l'a montré :

  **La dé-césure** ne fait pas baisser l'erreur — elle la fait monter. Son
  intérêt est de ne pas *punir* un correcteur qui recolle. Construite sur son
  nom, elle aurait été livrée avec la mauvaise justification, et le prochain
  lecteur l'aurait activée en croyant améliorer sa mesure.

  **La vision Ollama** n'était pas une fonctionnalité absente mais un
  **silence** : `role="text_only"` en dur alors que le planificateur passait
  déjà un `role`. L'interface laissait choisir le mode, le planificateur le
  déclarait, l'adapter l'ignorait, et rien ne le disait.

  **Les métriques d'identité** ont corrigé une phrase que j'avais écrite dans
  une docstring *et* dans un test — « tout se décale d'un cran ». Le test ne
  passait pas. J'aurais pu l'ajuster jusqu'à ce qu'il passe ; j'ai vérifié le
  mécanisme réel à la place.

  **Ce que je retiens** : un item de file nomme une intention, pas un fait. Le
  chiffrer avant de l'écrire coûte une heure et évite de livrer du code juste
  pour une raison fausse — ce qui est pire qu'un bug, parce que ça se propage
  dans la documentation et dans les décisions suivantes.

- 2026-08-21 — **Bilan de la journée : cinq défauts trouvés, tous dans ce qui
  vérifie plutôt que dans ce qui est vérifié.**

  Un contrat de docstring que personne n'implémentait (six lignes de campagne
  faussées). Un contrôle de ligne de base qui « ne tombait pas juste » et qu'il
  aurait été tentant de contourner. Deux erreurs symétriques dans le format
  ALTO qui s'annulaient et que neuf tests verrouillaient. Un mode d'exécution
  ignoré en silence. Un appariement de lignes qui déclare « aucune
  correspondance » pour des lignes quasi parfaites.

  Aucun n'était une valeur fausse dans un calcul. Tous étaient un contrôle
  absent, contourné, ou qui se comparait à lui-même.

- 2026-08-21 — **`docs/promises.md` se contredisait depuis trois jours.** Sa
  table listait 24 promesses toutes gardées ou fermées ; son texte narratif
  disait « restent cinq “aucune” ». Les cinq avaient été fermées le 19 août et
  personne n'avait relu le paragraphe qui les commentait.

  Ce n'est pas un détail de documentation. Le contrat de boucle dit qu'une
  session réveillée n'a que ces fichiers pour contexte : elle aurait ouvert
  trois arbitrages déjà tranchés. **Un fichier d'état qui se contredit
  lui-même est pire qu'un fichier absent, parce qu'on le croit.**

  Ce que ça ajoute aux règles : quand une table et sa prose divergent, la
  table fait foi — et la prose doit être relue à chaque changement de table,
  pas seulement écrite une fois.

- 2026-08-21 — **Six lignes vides en coûtaient quarante, et j'ai failli
  demander un arbitrage au lieu de regarder.**

  Le validateur refusait toute correction vide, pour empêcher un modèle
  d'**effacer** une ligne qui avait du contenu. Bonne règle. Mais il ne
  regardait pas la ligne source : quand celle-ci est **déjà vide**, il n'y a
  rien à effacer, et une réponse vide est la seule honnête.

  Conséquence mesurée sur `corpus/37-GT-BNL` : 6 lignes à OCR vide sur 522
  faisaient épuiser leurs tentatives à **4 lots de 12**, et chaque lot
  retombait en entier — jetant **40 corrections justes**. Une page réelle
  passait de 531 s / 0 correction à **88 s / 8 corrections**.

  **Ce n'était pas un arbitrage.** J'ai présenté ça au mainteneur comme un
  choix de conception à trancher — couverture totale contre lots partiels —
  alors qu'en ouvrant le validateur, le défaut était local et la garantie
  intacte : on n'efface toujours pas une ligne pleine. Le mainteneur a dû me
  dire « tu ne peux pas simplement lancer le run ? » pour que je regarde.

  **Ce que je retiens** : avant de demander un arbitrage, ouvrir le code. Une
  question de conception et un défaut de trois lignes se ressemblent beaucoup
  vus de loin, et seul l'un des deux justifie d'attendre.

  **Et le correctif lui-même a reproduit l'erreur du matin** : ma première
  version traitait « pas de texte source fourni » comme « source vide ». Les
  tests l'ont attrapée. *Absent n'est pas vide* — c'est la troisième fois
  aujourd'hui que cette confusion précise coûte quelque chose.

- 2026-08-22 — **L'arbitrage sur la couverture des lots est tranché : rien à
  changer.** Il avait été ouvert le 21 août après avoir observé qu'un lot entier
  retombait sur son texte d'origine à cause d'une seule ligne.

  Mesure après le correctif des lignes vides (`#161`), corpus complet
  `corpus/37-GT-BNL`, `gemma4:e2b` en local :

  | | |
  |---|---|
  | pages | 37 |
  | lignes | 522 |
  | appels au producteur | 40 |
  | **retries** | **2** |
  | **descentes de granularité** | **1** |
  | pages ayant eu besoin de l'un ou l'autre | **1 sur 37** |
  | lignes corrigées | 213 |

  **Les lignes vides étaient la cause de la totalité du phénomène.** Une fois
  qu'une ligne source vide a droit à une réponse vide, l'échec de lot devient
  marginal — un cas sur trente-sept.

  **Et le dilemme que j'avais présenté n'existait pas.** J'avais posé la question
  comme « couverture totale contre lots partiels ». Le code porte déjà une
  descente `PAGE → BLOC → FENÊTRE → LIGNE` : à granularité LIGNE, un échec ne
  coûte qu'une ligne. Le comportement « partiel » est donc **déjà là**, obtenu
  par découpage plutôt que par acceptation partielle.

  Reste un point noté et **non traité, faute de cas qui le déclenche** :
  `max_attempts = 3` par granularité contre `per_chunk_budget = 6` pour toute la
  descente. Trois essais au niveau BLOC consomment la moitié de la bourse, et les
  sous-lots suivants se la partagent — le premier la prend, les autres retombent
  sans avoir été tentés. Corriger ça aujourd'hui serait spéculatif : sur 37
  pages, une seule descente a eu lieu, et elle a abouti.

  **La leçon de méthode** : j'ai failli demander un arbitrage de conception pour
  un défaut de trois lignes dans un validateur. Avant de solliciter une décision,
  ouvrir le code — une question de conception et un bug se ressemblent beaucoup
  vus de loin, et seul l'un des deux justifie d'attendre.
