// SPDX-License-Identifier: LGPL-2.1-or-later
// Croquis - generic panel component. Adapted from ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, dtpanels/qml, LGPL-2.1-or-later).
// Versioned imports: works with Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

Item {
    id: row
    property var p: ({ name: "", label: "", kind: "", unit: "", tip: "", decimals: 2, step: 1, min: 0, max: 100, options: [], optionLabels: [], readonly: false })
    property var th: bridge.theme
    property string value: { var v = bridge.values[p.name]; return v ? v : "#000000" }
    implicitHeight: Math.round(28 * th.s)
    width: parent ? parent.width : 0

    Text {
        anchors.verticalCenter: parent.verticalCenter
        text: row.p.label
        color: th.text
        font.pixelSize: Math.round(12 * th.s); font.family: th.family
    }
    Rectangle {
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: Math.round(96 * th.s); height: Math.round(22 * th.s)
        radius: Math.round(4 * th.s)
        color: th.field
        Rectangle {
            x: 4; anchors.verticalCenter: parent.verticalCenter
            width: Math.round(16 * th.s); height: width; radius: 3
            color: row.value
            border.color: th.line
        }
        Text {
            anchors.right: parent.right; anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            text: row.value
            color: th.text
            font.pixelSize: Math.round(11 * th.s); font.family: th.family
        }
        MouseArea { anchors.fill: parent; onClicked: bridge.pickColor(row.p.name) }
    }
}
