# Croquis : un atelier « paint de designer » pour FreeCAD

> **Croquis** : *Designer-style sketching for FreeCAD: pencil, marker and tapered spline strokes, rendered as translucent image planes.*

## 1. Le nom

| Nom | Pour | Contre |
|---|---|---|
| **Croquis** (recommandé) | Court, compris par les designers du monde entier (le mot est utilisé tel quel en anglais pour le dessin rapide). Il dit exactement ce que c'est. Il ne se confond pas avec le Sketcher (paramétrique). | Mot français dans une interface anglaise, mais c'est plutôt un charme qu'un défaut. |
| **Layout Pad** | Le « layout pad » est le papier translucide des designers, sur lequel on calque et on passe le feutre. Ça colle à l'idée de translucidité. | Moins parlant hors du monde du design produit. |
| **Marker Sketch** | Très descriptif. | Réducteur : l'atelier fait aussi le portemine et le trait spline. |
| **Tracing** | Évoque le calque posé sur la vue 3D. | Trop générique, se confond avec le « tracé » d'images vectorielles. |

À éviter : **Vellum** (c'est déjà le nom d'un logiciel de CAO, Ashlar-Vellum) et tout ce qui contient « Pro ».

À faire avant de figer le nom : vérifier qu'aucun addon de l'index FreeCAD ne s'appelle déjà ainsi.

## 2. L'idée en une phrase

Aujourd'hui, on dessine ses croquis ailleurs (papier, tablette, Photoshop, Sketchbook), puis on les **importe comme images** dans FreeCAD (atelier Image, plan d'image) pour modéliser par-dessus. **Croquis** permet de faire ces images **directement dans FreeCAD** : le résultat est le même objet qu'une image importée (un `Image::ImagePlane` placé dans la scène), mais il reste **éditable**, parce que les traits sont stockés dans le document.

Deux usages principaux :

1. **Croquis d'intention avant modélisation** : on dessine une vue de profil ou en perspective, on la pose sur un plan, et on modélise par-dessus, comme avec une image importée.
2. **Overpaint (calque sur la 3D)** : on capture la vue 3D courante, on la pose en fond à faible opacité, et on dessine par-dessus au feutre pour explorer des variantes. C'est le geste classique du design produit : imprimer une vue, poser un calque, repasser au feutre.

## 3. Le rendu visé

Le style « croquis design » se reconnaît à quelques codes qu'il faut reproduire fidèlement :

- **Trait fusiforme** : fin au départ, gras au centre, pointu à la sortie. C'est la signature du trait de designer, lancé d'un geste.
- **Débords** : les traits de construction dépassent les intersections, ils ne s'arrêtent pas net aux angles.
- **Hiérarchie de traits** : construction très légère au portemine, contours au crayon gras ou au trait spline, contour extérieur (silhouette) plus épais que les lignes intérieures.
- **Feutre translucide superposé** : chaque passage de feutre à alcool fonce la zone. Les gris froids et chauds (type Copic CG / WG, N0 à N9) donnent le volume.
- **Rehauts** : quelques touches de blanc (crayon blanc, gouache) pour les reflets, surtout sur papier teinté.
- **Translucidité** : le croquis entier est un calque. Le fond peut être transparent pour qu'on voie la 3D au travers.

## 4. Les outils

### 4.1 Portemine (0,5 mm, mine HB à 2B)

- Trait fin, gris, **la pression agit surtout sur l'opacité**, peu sur la largeur.
- Texture de grain graphite légère (texture appliquée le long du trait).
- Usage : construction, axes, ellipses, perspective.

### 4.2 Crayon gras (type Prismacolor noir, Stabilo All)

- Trait plus large, **la pression agit sur la largeur et la densité**.
- Grain marqué qui laisse apparaître le papier aux faibles pressions.
- Usage : contours affirmés, ombres portées rapides, silhouette.

### 4.3 Feutre à alcool (type Copic, Promarker)

- **Translucide, mode de fusion « produit » (multiply)**.
- Point technique clé : un trait ne doit **pas foncer sur lui-même**, mais deux traits superposés doivent foncer. Pour cela, on rend chaque trait dans un tampon séparé à opacité pleine, puis on le compose sur le calque avec l'opacité du feutre.
- Pointe biseautée (chisel) : la largeur dépend de l'angle du trait. Pointe ogive en option.
- Léger assombrissement des bords pour imiter l'encre qui migre dans le papier.
- Palettes intégrées : gris froids, gris chauds, gris neutres, plus quelques couleurs d'accent.

### 4.4 Trait spline (le « fin, pointu, gras au centre »)

C'est l'outil vectoriel, le plus « design » :

- **Deux modes de saisie** :
  - **main levée lissée** : on dessine librement, puis la trajectoire est ajustée en courbe de Bézier (algorithme de Schneider) ;
  - **points de contrôle** : on pose des points comme une B-spline du Sketcher.
- **Profil de largeur réglable** : largeur max, position du pic (au centre ou décalée vers l'avant), effilement d'entrée et de sortie. Par défaut, une forme du type `w(t) = w_max · sin(π·t)^k`.
- Le trait est construit comme un **contour rempli** (décalage de la courbe de part et d'autre selon la normale), donc net à toutes les échelles.
- Reste éditable après coup : on peut reprendre un point, la largeur ou l'effilement.

### 4.5 Outils annexes

- **Règle** : ligne droite en maintenant Maj, avec effilement conservé.
- **Ellipses guidées** : l'ellipse est l'exercice de base du designer. Outil d'ellipse avec petit axe orienté selon la perspective.
- **Grilles de perspective** 1, 2 et 3 points, en calque de guide non exporté.
- **Rehaut blanc** : crayon blanc et touche de gouache opaque.
- **Gomme** : douce (graphite) et dure (vectorielle, coupe les traits).

## 5. Calques et papier

Calques par défaut, dans l'ordre :

1. **Fond** : transparent, blanc, papier layout, gris teinté ou kraft.
2. **Sous-couche** : capture de la vue 3D ou image importée, opacité réglable.
3. **Construction** : portemine.
4. **Feutre** : couches de gris en multiply.
5. **Traits** : crayon gras et traits spline.
6. **Rehauts** : blanc.

Chaque calque a une opacité, un mode de fusion et un interrupteur de visibilité. L'export peut exclure la sous-couche, pour obtenir un PNG transparent qui se superpose proprement à la 3D.

## 6. Architecture technique

### 6.1 Principe

- Atelier Python pur, Qt via le module `PySide` de FreeCAD (compatible Qt5 en 1.0 et Qt6 en 1.1).
- **Planche de dessin** : une sous-fenêtre MDI (comme un onglet de document ou une page TechDraw) contenant une `QGraphicsView`. On dessine en 2D, à plat, dans de bonnes conditions, sans lutter avec la caméra 3D.
- **Saisie tablette** : `QTabletEvent` pour la pression et l'inclinaison. À la souris, on simule la pression à partir de la vitesse (trait rapide = plus fin).
- **Capture de la vue 3D** pour la sous-couche : `ActiveView.saveImage()` avec un fond transparent, et mémorisation de la caméra pour pouvoir la restaurer.

### 6.2 Objets dans le document

- **`Croquis::Sheet`** (FeaturePython) : contient les traits sous forme de données (JSON : outil, couleur, points `x, y, pression, temps`, paramètres de profil), les calques, le papier, la caméra associée.
- **Un `Image::ImagePlane` lié** : c'est le rendu PNG, placé dans la scène. C'est exactement ce qu'on obtiendrait avec une image importée, donc tout ce qui marche avec une image importée marche ici.
- **Double-clic** sur l'objet : rouvre la planche pour retoucher. À la fermeture, le PNG est régénéré.
- Placement du plan d'image au choix : plan XY, XZ ou YZ, face sélectionnée, ou **plan de la caméra** (pour l'overpaint, le croquis se superpose pile à la vue d'où il a été capturé).

### 6.3 Rendu

- Traits raster (portemine, crayon gras, feutre) : rendus dans des `QImage` par tuiles, avec mise en cache, pour garder la fluidité sur de grandes planches.
- Traits spline : `QPainterPath` remplis, rendus au dernier moment à la résolution d'export.
- Annuler/rétablir : `QUndoStack` au niveau des traits.
- Résolution de la planche réglable (par exemple A4 à 150 ou 300 dpi).

### 6.4 Exports

- **PNG transparent** (principal).
- **SVG** : traits spline en vectoriel, traits texturés en raster intégré.
- Possibilité ultérieure : envoyer un croquis dans une page TechDraw (planche de présentation).

## 7. Arborescence proposée

```
Croquis/
├── package.xml
├── LICENSE                  (LGPL-2.1)
├── README.md
├── Init.py
├── InitGui.py
├── croquis/
│   ├── commands.py          (commandes et barre d'outils)
│   ├── sheet.py             (FeaturePython Croquis::Sheet + ViewProvider)
│   ├── canvas/
│   │   ├── view.py          (QGraphicsView, MDI, saisie tablette)
│   │   ├── layers.py
│   │   └── undo.py
│   ├── tools/
│   │   ├── pencil.py        (portemine)
│   │   ├── grease.py        (crayon gras)
│   │   ├── marker.py        (feutre à alcool)
│   │   ├── spline.py        (trait spline fusiforme)
│   │   ├── ellipse.py
│   │   └── eraser.py
│   ├── render/
│   │   ├── stroke_geom.py   (lissage, ajustement Bézier, profils de largeur)
│   │   ├── textures.py      (grain graphite, papier)
│   │   └── compositor.py    (calques, multiply, export PNG/SVG)
│   └── capture.py           (capture de la vue 3D, placement du plan d'image)
└── resources/
    ├── icons/
    ├── textures/
    └── palettes/            (gris CG / WG / N)
```

## 8. Feuille de route

**v0.1 : la planche qui marche**
- Planche MDI, portemine et feutre, pression tablette, annuler/rétablir.
- Export PNG transparent et création du plan d'image.

**v0.2 : le style design**
- Trait spline fusiforme (main levée lissée et points de contrôle).
- Crayon gras, calques, papiers.
- Édition par double-clic, traits stockés dans le document.

**v0.3 : images, captures et annotations**
- Images collées ou importées (presse-papiers, glisser-déposer, fichier), nouvelle feuille depuis le presse-papiers, calque `images`, format de feuille v2.
- Capture manuelle de la vue 3D pour la commenter.
- Sous-couche vue 3D (guide non exporté) : vue alignée sur le plan de la feuille, puis vue caméra (overpaint).
- Outil flèche, zones de texte et légendes.
- Toujours prévus : ellipses guidées, grilles de perspective, rehauts avancés.

**v0.4 et au-delà**
- Export SVG, envoi vers TechDraw.
- Pointe biseautée sensible à l'inclinaison, palettes personnalisées.

## 9. Risques et points à vérifier

- **Pression des tablettes sous Linux** : variable selon X11 ou Wayland et le pilote. Prévoir un réglage de courbe de pression et le mode souris par vitesse.
- **Fluidité** : le rendu Python peut ralentir sur les grandes planches. Les tuiles et le cache sont indispensables dès la v0.1.
- **Qt5 / Qt6** : passer par le module `PySide` de FreeCAD et éviter les API qui diffèrent entre les deux.
- **Poids des fichiers** : un PNG haute résolution par croquis alourdit le `.FCStd`. Prévoir une résolution par défaut raisonnable.
- **Rendu du feutre** : la règle « un trait ne fonce pas sur lui-même » est ce qui fait la différence entre un vrai rendu Copic et un simple pinceau transparent. C'est le point à soigner en priorité.
