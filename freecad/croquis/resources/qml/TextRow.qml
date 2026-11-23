// SPDX-License-Identifier: LGPL-2.1-or-later
// Croquis - generic panel component (one line of text).
// Versioned imports: works with Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

Item {
    id: row
    property var p: ({ name: "", label: "", kind: "", unit: "", tip: "", decimals: 2, step: 1, min: 0, max: 100, options: [], optionLabels: [], readonly: false })
    property var th: bridge.theme
    property string value: { var v = bridge.values[p.name]; return v ? String(v) : "" }
    implicitHeight: Math.round(28 * th.s)
    width: parent ? parent.width : 0

    Text {
        id: lab
        anchors.verticalCenter: parent.verticalCenter
        text: row.p.label
        color: th.text
        font.pixelSize: Math.round(12 * th.s); font.family: th.family
    }
    Rectangle {
        anchors.right: parent.right
        anchors.left: lab.right
        anchors.leftMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        height: Math.round(24 * th.s)
        radius: Math.round(4 * th.s)
        color: th.field
        border.width: input.activeFocus ? 1 : 0
        border.color: th.accent
        TextInput {
            id: input
            objectName: "input_" + row.p.name
            anchors.fill: parent; anchors.margins: 6
            color: th.text
            selectionColor: th.accent
            selectByMouse: true
            clip: true
            readOnly: row.p.readonly === true
            font.pixelSize: Math.round(12 * th.s); font.family: th.family
            text: row.value
            onEditingFinished: bridge.setValue(row.p.name, text)
        }
    }
}
