import QtQuick
import Quickshell
import Quickshell.Io
import qs.Commons
import qs.Ui

Panel {
  id: root
  moduleName: "avendor7.twitch"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  property bool settingsPage: false
  property var snapshot: ({ streams: [], follows: [], config: { poll_interval: 90 } })
  property string localError: ""
  readonly property var barIdentity: hostWidget || root
  readonly property string helper: Qt.resolvedUrl("../bin/omarchy-twitch").toString().replace("file://", "")

  function open() {
    controller.show()
    refresh(false)
  }

  function close() { controller.hide() }
  function toggle() { opened ? close() : open() }

  function refresh(force) {
    if (pollProcess.running) return
    pollProcess.command = force ? [helper, "poll", "--force"] : [helper, "poll"]
    pollProcess.running = true
  }

  function runAction(args) {
    if (actionProcess.running) return
    localError = ""
    actionProcess.command = [helper].concat(args)
    actionProcess.running = true
  }

  function configValue(key, fallback) {
    var cfg = snapshot.config || {}
    return cfg[key] === undefined ? fallback : cfg[key]
  }

  function uptime(started) {
    var elapsed = Math.max(0, Math.floor((Date.now() - Date.parse(started)) / 60000))
    if (isNaN(elapsed)) return ""
    var hours = Math.floor(elapsed / 60)
    return "Live " + (hours ? hours + "h " : "") + (elapsed % 60) + "m"
  }

  function overrideFor(login) {
    var overrides = configValue("notification_overrides", {})
    if (overrides[login] === undefined) return configValue("notify_all", true)
    return overrides[login]
  }

  function toggleOverride(login) {
    runAction(["notify-channel", login, overrideFor(login) ? "off" : "on"])
  }

  Process {
    id: pollProcess
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var value = JSON.parse(String(text || "{}"))
          root.snapshot = value
          if (root.hostWidget) root.hostWidget.snapshot = value
        } catch (error) {
          root.localError = "Could not read Twitch helper response"
        }
      }
    }
  }

  Process {
    id: actionProcess
    stdout: StdioCollector {
      waitForEnd: true
      onStreamFinished: {
        try {
          var value = JSON.parse(String(text || "{}"))
          if (value.error) root.localError = value.error
        } catch (error) {
          root.localError = "Could not save Twitch setting"
        }
      }
    }
    onExited: function(exitCode) {
      if (exitCode !== 0 && !root.localError) root.localError = "Twitch setting failed"
      root.refresh(true)
    }
  }

  Timer {
    interval: Math.max(60, Math.min(900, Number(root.configValue("poll_interval", 90)))) * 1000
    running: true
    repeat: true
    triggeredOnStart: true
    onTriggered: root.refresh(false)
  }

  KeyboardPanel {
    id: popup
    anchorItem: root.anchorItem
    owner: root.barIdentity
    bar: root.bar
    open: root.opened
    centerOnBar: true
    contentWidth: fittedContentWidth(Style.space(460))
    contentHeight: fittedContentHeight(panelColumn.implicitHeight)
    focusTarget: keyCatcher

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: channelField.activeFocus || importField.activeFocus || clientField.activeFocus
      onCloseRequested: root.close()
      onTextKey: function(value) {
        if (value === "r") root.refresh(true)
      }

      Flickable {
        id: scroll
        anchors.fill: parent
        clip: true
        contentWidth: width
        contentHeight: panelColumn.implicitHeight
        boundsBehavior: Flickable.StopAtBounds

        Column {
          id: panelColumn
          width: scroll.width
          spacing: Style.space(12)

          Row {
            width: parent.width
            spacing: Style.space(10)

            Text {
              width: parent.width - liveButton.width - settingsButton.width - Style.space(20)
              text: "Twitch  ·  " + (root.snapshot.streams || []).length + " live"
              color: Color.foreground
              font.family: Style.font.family
              font.pixelSize: Style.font.title
              font.bold: true
            }
            Button {
              id: liveButton
              text: "Live"
              selected: !root.settingsPage
              onClicked: root.settingsPage = false
            }
            Button {
              id: settingsButton
              text: "Settings"
              selected: root.settingsPage
              onClicked: root.settingsPage = true
            }
          }

          Text {
            visible: root.localError !== "" || !!root.snapshot.error
            width: parent.width
            wrapMode: Text.Wrap
            textFormat: Text.PlainText
            text: root.localError || root.snapshot.error || ""
            color: Color.urgent
            font.pixelSize: Style.font.body
          }

          Text {
            visible: !!root.snapshot.warning
            width: parent.width
            wrapMode: Text.Wrap
            textFormat: Text.PlainText
            text: root.snapshot.warning || ""
            color: Color.muted
            font.pixelSize: Style.font.body
          }

          Column {
            visible: !root.settingsPage
            width: parent.width
            spacing: Style.space(8)

            Text {
              visible: (root.snapshot.streams || []).length === 0
              width: parent.width
              text: "No followed channels are live. Open Settings to add or import follows."
              textFormat: Text.PlainText
              wrapMode: Text.Wrap
              color: Color.foreground
              font.pixelSize: Style.font.body
            }

            Repeater {
              model: root.snapshot.streams || []
              delegate: Rectangle {
                required property var modelData
                width: panelColumn.width
                height: streamInfo.implicitHeight + Style.space(18)
                color: streamMouse.containsMouse ? Color.popups.background : "transparent"
                radius: Style.cornerRadius

                Column {
                  id: streamInfo
                  anchors.left: parent.left
                  anchors.right: parent.right
                  anchors.verticalCenter: parent.verticalCenter
                  anchors.leftMargin: Style.space(8)
                  anchors.rightMargin: Style.space(8)
                  spacing: Style.space(3)
                  Text {
                    width: parent.width
                    text: "●  " + modelData.display_name + "  ·  " + Number(modelData.viewers).toLocaleString() + " viewers"
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    color: Color.accent
                    font.bold: true
                    font.pixelSize: Style.font.body
                  }
                  Text {
                    width: parent.width
                    text: modelData.title || "Untitled stream"
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    color: Color.foreground
                    font.pixelSize: Style.font.body
                  }
                  Text {
                    width: parent.width
                    text: (modelData.game || "No category") + "  ·  " + root.uptime(modelData.started_at)
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                    color: Color.muted
                    font.pixelSize: Style.font.caption
                  }
                }
                MouseArea {
                  id: streamMouse
                  anchors.fill: parent
                  hoverEnabled: true
                  cursorShape: Qt.PointingHandCursor
                  onClicked: Qt.openUrlExternally(modelData.url)
                }
              }
            }
            Button {
              text: "Refresh"
              onClicked: root.refresh(true)
            }
          }

          Column {
            visible: root.settingsPage
            width: parent.width
            spacing: Style.space(9)

            Text {
              text: "Follow source"
              color: Color.foreground
              font.bold: true
            }
            Flow {
              width: parent.width
              spacing: Style.space(4)
              Repeater {
                model: [
                  { key: "auto", label: "Browser auto" },
                  { key: "manual", label: "Manual list" },
                  { key: "import", label: "Export file" },
                  { key: "token", label: "Session token" },
                  { key: "helix", label: "Helix OAuth" }
                ]
                delegate: Button {
                  required property var modelData
                  text: modelData.label
                  selected: root.configValue("mode", "auto") === modelData.key
                  onClicked: root.runAction(["set", "mode", modelData.key])
                }
              }
            }
            Text {
              width: parent.width
              wrapMode: Text.Wrap
              textFormat: Text.PlainText
              color: Color.muted
              text: "Source: " + (root.snapshot.source || "none") + ". Browser auto checks Firefox, Chrome, Chromium and Brave; saved channels are used when no session is readable."
            }

            Row {
              spacing: Style.space(6)
              Button {
                text: root.configValue("notifications", true) ? "Notifications on" : "Notifications off"
                onClicked: root.runAction(["set", "notifications", root.configValue("notifications", true) ? "false" : "true"])
              }
              Button {
                text: root.configValue("notify_all", true) ? "All follows" : "Overrides only"
                onClicked: root.runAction(["set", "notify_all", root.configValue("notify_all", true) ? "false" : "true"])
              }
            }
            Button {
              text: "Poll every " + root.configValue("poll_interval", 90) + "s"
              onClicked: {
                var values = [60, 90, 120, 180, 300]
                var index = values.indexOf(root.configValue("poll_interval", 90))
                root.runAction(["set", "poll_interval", String(values[(index + 1) % values.length])])
              }
            }

            Text { text: "Add a channel"; color: Color.foreground; font.bold: true }
            Row {
              spacing: Style.space(5)
              TextField {
                id: channelField
                width: panelColumn.width - addButton.width - Style.space(5)
                placeholderText: "twitch login"
                onAccepted: addButton.clicked()
              }
              Button {
                id: addButton
                text: "Add"
                onClicked: {
                  root.runAction(["follow", "add", channelField.text])
                  channelField.text = ""
                }
              }
            }
            Text { text: "Import Twitch follow export"; color: Color.foreground; font.bold: true }
            Row {
              spacing: Style.space(5)
              TextField {
                id: importField
                width: panelColumn.width - importButton.width - Style.space(5)
                placeholderText: "~/Downloads/twitch-follows.json"
                onAccepted: importButton.clicked()
              }
              Button {
                id: importButton
                text: "Import"
                onClicked: root.runAction(["follow", "import", importField.text])
              }
            }

            Text {
              visible: root.configValue("mode", "auto") === "token" || root.configValue("mode", "auto") === "helix"
              width: parent.width
              wrapMode: Text.Wrap
              textFormat: Text.PlainText
              color: Color.muted
              text: "Store a token privately in a terminal: ~/.config/omarchy/plugins/avendor7.twitch/bin/omarchy-twitch auth set. The token is read with a hidden prompt and saved in Secret Service."
            }
            Row {
              visible: root.configValue("mode", "auto") === "helix"
              spacing: Style.space(5)
              TextField {
                id: clientField
                width: panelColumn.width - clientButton.width - Style.space(5)
                placeholderText: "Twitch Client ID"
                text: root.configValue("client_id", "")
              }
              Button {
                id: clientButton
                text: "Save ID"
                onClicked: root.runAction(["set", "client_id", clientField.text])
              }
            }

            Text { text: "Channel notifications"; color: Color.foreground; font.bold: true }
            Repeater {
              model: root.snapshot.follows || []
              delegate: Row {
                required property string modelData
                width: panelColumn.width
                spacing: Style.space(6)
                Text {
                  width: parent.width - notifyButton.width - Style.space(6)
                  text: modelData
                  textFormat: Text.PlainText
                  elide: Text.ElideRight
                  color: Color.foreground
                }
                Button {
                  id: notifyButton
                  text: root.overrideFor(modelData) ? "Notify" : "Muted"
                  onClicked: root.toggleOverride(modelData)
                }
              }
            }
          }
        }
      }
    }
  }
}
