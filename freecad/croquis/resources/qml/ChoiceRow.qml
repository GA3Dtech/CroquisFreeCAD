// SPDX-License-Identifier: LGPL-2.1-or-later
// Croquis - generic panel component. Adapted from ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, dtpanels/qml, LGPL-2.1-or-later).
// Versioned imports: works with Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

Item {
    id: row
    property var p: ({ name: "", label: "", kind: "", unit: "", tip: "", decimals: 2, step: 1, min: 0, max: 100, options: [], optionLabels: [], readonly: false })
    property var th: bridge.theme
    property string value: { var v = bridge.values[p.name]; return v === undefined || v === null ? "" : String(v) }
    implicitHeight: col.implicitHeight + 4
    width: parent ? parent.width : 0

    Column {
        id: col
        width: parent.width
        spacing: Math.round(4 * th.s)
        Text {
            text: row.p.label
            color: th.text
            font.pixelSize: Math.round(12 * th.s); font.family: th.family
        }
        Flow {
            width: parent.width
            spacing: Math.round(4 * th.s)
            Repeater {
                model: row.p.options
                Rectangle {
                    property bool sel: String(modelData) === row.value
                    width: lab.implicitWidth + Math.round(16 * th.s)
                    height: Math.round(24 * th.s)
                    radius: Math.round(6 * th.s)
                    color: sel ? th.accent : th.field
                    Text {
                        id: lab
                        anchors.centerIn: parent
                        text: row.p.optionLabels[index]
                        color: parent.sel ? th.accentText : th.text
                        font.bold: parent.sel
                        font.pixelSize: Math.round(11 * th.s); font.family: th.family
                    }
                    MouseArea {
                        anchors.fill: parent
                        enabled: row.p.readonly !== true
                        onClicked: bridge.setValue(row.p.name, modelData)
                    }
                }
            }
        }
    }
}
