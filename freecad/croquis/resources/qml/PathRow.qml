// SPDX-License-Identifier: LGPL-2.1-or-later
// Croquis - generic panel component. Adapted from ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, dtpanels/qml, LGPL-2.1-or-later).
// Versioned imports: works with Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

Item {
    id: row
    property var p: ({ name: "", label: "", kind: "", unit: "", tip: "", decimals: 2, step: 1, min: 0, max: 100, options: [], optionLabels: [], readonly: false })
    property var th: bridge.theme
    property string value: { var v = bridge.values[p.name]; return v ? v : "" }
    implicitHeight: col.implicitHeight
    width: parent ? parent.width : 0

    Column {
        id: col
        width: parent.width
        spacing: 2
        Text {
            text: row.p.label
            color: th.text
            font.pixelSize: Math.round(12 * th.s); font.family: th.family
        }
        Row {
            width: parent.width
            spacing: Math.round(4 * th.s)
            Rectangle {
                width: parent.width - browse.width - 4; height: Math.round(24 * th.s)
                radius: Math.round(4 * th.s)
                color: th.field
                TextInput {
                    anchors.fill: parent; anchors.margins: 6
                    color: th.text
                    selectByMouse: true
                    clip: true
                    font.pixelSize: Math.round(11 * th.s); font.family: th.family
                    text: row.value
                    onEditingFinished: bridge.setValue(row.p.name, text)
                }
            }
            PillButton {
                id: browse
                th: row.th
                label: i18n.tr("Browse…")
                onClicked: bridge.browse(row.p.name)
            }
        }
    }
}
