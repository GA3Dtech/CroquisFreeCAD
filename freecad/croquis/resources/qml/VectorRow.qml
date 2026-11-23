// SPDX-License-Identifier: LGPL-2.1-or-later
// Croquis - generic panel component. Adapted from ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, dtpanels/qml, LGPL-2.1-or-later).
// Versioned imports: works with Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

Item {
    id: row
    property var p: ({ name: "", label: "", kind: "", unit: "", tip: "", decimals: 2, step: 1, min: 0, max: 100, options: [], optionLabels: [], readonly: false })
    property var th: bridge.theme
    property var value: { var v = bridge.values[p.name]; return v ? v : [0, 0, 0] }
    implicitHeight: col.implicitHeight
    width: parent ? parent.width : 0

    function commit(i, t) {
        var v = [row.value[0], row.value[1], row.value[2]]
        var x = parseFloat(t.replace(",", "."))
        if (isNaN(x)) return
        v[i] = x
        bridge.setValue(row.p.name, v)
    }

    Column {
        id: col
        width: parent.width
        spacing: 2
        Text {
            text: row.p.label + (row.p.unit ? " (" + row.p.unit + ")" : "")
            color: th.text
            font.pixelSize: Math.round(12 * th.s); font.family: th.family
        }
        Row {
            spacing: Math.round(4 * th.s)
            Repeater {
                model: 3
                Rectangle {
                    width: (col.width - 8) / 3; height: Math.round(24 * th.s)
                    radius: Math.round(4 * th.s)
                    color: th.field
                    TextInput {
                        anchors.fill: parent; anchors.margins: 6
                        horizontalAlignment: TextInput.AlignRight
                        color: th.text
                        selectByMouse: true
                        clip: true
                        font.pixelSize: Math.round(12 * th.s); font.family: th.family
                        text: Number(row.value[index]).toFixed(row.p.decimals)
                        onEditingFinished: row.commit(index, text)
                    }
                }
            }
        }
    }
}
