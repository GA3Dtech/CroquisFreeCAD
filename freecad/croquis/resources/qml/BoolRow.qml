// SPDX-License-Identifier: LGPL-2.1-or-later
// Croquis - generic panel component. Adapted from ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, dtpanels/qml, LGPL-2.1-or-later).
// Versioned imports: works with Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

Item {
    id: row
    property var p: ({ name: "", label: "", kind: "", unit: "", tip: "", decimals: 2, step: 1, min: 0, max: 100, options: [], optionLabels: [], readonly: false })
    property var th: bridge.theme
    property bool value: bridge.values[p.name] === true
    implicitHeight: Math.round(28 * th.s)
    width: parent ? parent.width : 0

    Text {
        anchors.verticalCenter: parent.verticalCenter
        anchors.left: parent.left
        anchors.right: knob.left
        text: row.p.label
        color: th.text
        elide: Text.ElideRight
        font.pixelSize: Math.round(12 * th.s); font.family: th.family
    }
    Rectangle {
        id: knob
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: Math.round(36 * th.s); height: Math.round(20 * th.s)
        radius: height / 2
        color: row.value ? th.accent : th.line
        Rectangle {
            width: parent.height - 4; height: width; radius: width / 2
            y: 2; x: row.value ? parent.width - width - 2 : 2
            color: "#ffffff"
        }
        MouseArea {
            anchors.fill: parent
            enabled: row.p.readonly !== true
            onClicked: bridge.setValue(row.p.name, !row.value)
        }
    }
}
