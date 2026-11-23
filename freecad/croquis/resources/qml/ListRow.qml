// SPDX-License-Identifier: LGPL-2.1-or-later
// Croquis - generic panel component. Adapted from ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, dtpanels/qml, LGPL-2.1-or-later).
// Versioned imports: works with Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

Column {
    id: row
    property var p: ({ name: "", label: "", kind: "", unit: "", tip: "", decimals: 2, step: 1, min: 0, max: 100, options: [], optionLabels: [], readonly: false })
    property var th: bridge.theme
    property var value: { var v = bridge.values[p.name]; return v ? v : [] }
    width: parent ? parent.width : 0
    spacing: 2
    Text {
        visible: row.p.label ? true : false
        text: row.p.label ? row.p.label : ""
        color: th.text
        font.pixelSize: Math.round(12 * th.s); font.family: th.family
    }
    Repeater {
        model: row.value
        Text {
            width: row.width
            text: String(modelData)
            color: th.text
            elide: Text.ElideRight
            font.pixelSize: Math.round(11 * th.s); font.family: th.family
        }
    }
}
