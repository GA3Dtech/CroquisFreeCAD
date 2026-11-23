// SPDX-License-Identifier: LGPL-2.1-or-later
// Croquis - generic panel component. Adapted from ShowRoom
// (https://github.com/oficinerobotica/ShowRoom, dtpanels/qml, LGPL-2.1-or-later).
// Versioned imports: works with Qt 5 (FreeCAD 1.0) and Qt 6 (FreeCAD 26.x).
import QtQuick 2.15

Rectangle {
    id: pill
    property var th: bridge.theme
    property string label: ""
    property bool primary: false
    property bool active: false
    signal clicked()
    width: txt.implicitWidth + Math.round(20 * th.s)
    height: Math.round(26 * th.s)
    radius: height / 2
    color: primary || active ? th.accent : (ma.containsMouse ? th.line : th.field)
    Text {
        id: txt
        anchors.centerIn: parent
        text: pill.label
        color: pill.primary || pill.active ? th.accentText : th.text
        font.pixelSize: Math.round(12 * th.s); font.family: th.family
    }
    MouseArea { id: ma; anchors.fill: parent; hoverEnabled: true; onClicked: pill.clicked() }
}
