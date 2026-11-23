// SPDX-License-Identifier: LGPL-2.1-or-later
// Croquis - generic panel component. Adapted from ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, dtpanels/qml, LGPL-2.1-or-later).
// Versioned imports: works with Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

Item {
    id: row
    property var p: ({ name: "", label: "", kind: "", unit: "", tip: "", decimals: 2, step: 1, min: 0, max: 100, options: [], optionLabels: [], readonly: false })
    property var th: bridge.theme
    property real value: { var v = bridge.values[p.name]; return v === undefined || v === null ? 0 : v }
    implicitHeight: Math.round(28 * th.s)
    width: parent ? parent.width : 0

    function commit(v) { if (!isNaN(v)) bridge.setValue(p.name, v) }
    function fmt(v) { return Number(v).toFixed(p.decimals) }

    Text {
        anchors.left: parent.left
        anchors.right: field.left
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        text: p.label
        color: th.text
        elide: Text.ElideRight
        font.pixelSize: Math.round(12 * th.s); font.family: th.family
    }
    Rectangle {
        id: field
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        width: Math.round(76 * th.s); height: Math.round(24 * th.s)
        radius: Math.round(4 * th.s)
        color: th.field
        border.width: input.activeFocus ? 1 : 0
        border.color: th.accent
        TextInput {
            id: input
            objectName: "input_" + row.p.name
            anchors.left: parent.left
            anchors.right: unit.left
            anchors.margins: 6
            anchors.verticalCenter: parent.verticalCenter
            horizontalAlignment: TextInput.AlignRight
            readOnly: row.p.readonly === true
            color: th.text
            selectionColor: th.accent
            selectByMouse: true
            clip: true
            font.pixelSize: Math.round(12 * th.s); font.family: th.family
            text: row.fmt(row.value)
            onEditingFinished: {
                row.commit(parseFloat(text.replace(",", ".")))
                text = Qt.binding(function() { return row.fmt(row.value) })
            }
            Keys.onUpPressed: row.commit(row.value + row.p.step)
            Keys.onDownPressed: row.commit(row.value - row.p.step)
        }
        Text {
            id: unit
            anchors.right: parent.right
            anchors.rightMargin: 6
            anchors.verticalCenter: parent.verticalCenter
            text: row.p.unit
            color: th.muted
            font.pixelSize: Math.round(11 * th.s); font.family: th.family
        }
    }
}
