using System;
using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using Tcg.Protocol;
using Tcg.View;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace Tcg.Board
{
    /// <summary>
    /// The prompt for an ability waiting on your choice (state.pending): the source card's name
    /// and text, so the choice keeps its context, plus a button per answer that isn't a card
    /// (Yes / No, choose-one options). Card answers (choose_target) are tapped on the board, where
    /// they're highlighted, in play or in your hand. The AI's choices aren't shown: the spotlight
    /// already showed its card. It sits over the middle of the board, so it can be hidden to see
    /// the cards under it, and brought back with a pill at the right end of the divider.
    /// </summary>
    public class ChoiceBanner : MonoBehaviour
    {
        const float DividerY = 270f;

        public event Action<GameAction> AnswerChosen;

        TMP_Text _text, _hint;
        RectTransform _buttons;
        GameObject _showButton;
        bool _collapsed;
        string _shown;  // which choice is up, so a new one opens again
        readonly List<GameObject> _built = new List<GameObject>();

        public static ChoiceBanner Create(RectTransform parent)
        {
            var root = Ui.Node("Choice", parent);
            Ui.Anchor(root, new Vector2(0.5f, 1), new Vector2(0.5f, 0.5f), new Vector2(0, -DividerY), new Vector2(880, 60));
            var view = root.gameObject.AddComponent<ChoiceBanner>();
            Ui.Panel(root, 16, Palette.Firefly.WithAlpha(0.8f), 0.92f).raycastTarget = true;
            var layout = root.gameObject.AddComponent<VerticalLayoutGroup>();
            layout.padding = new RectOffset(20, 20, 10, 12);
            layout.spacing = 8;
            layout.childAlignment = TextAnchor.UpperCenter;
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;
            root.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;

            view._text = Ui.Text(Ui.Node("Text", root), "", Ui.Theme.Body, 15, Palette.LanternText, TextAlignmentOptions.Center);
            view._text.textWrappingMode = TextWrappingModes.Normal;
            view._hint = Ui.Text(Ui.Node("Hint", root), UiText.ChooseHint, Ui.Theme.BodyBold, 13, Palette.Firefly,
                TextAlignmentOptions.Center);
            view._buttons = Ui.Node("Buttons", root);
            var size = view._buttons.gameObject.AddComponent<LayoutElement>();
            size.minHeight = size.preferredHeight = 48;
            var row = view._buttons.gameObject.AddComponent<HorizontalLayoutGroup>();
            row.spacing = 12;
            row.childAlignment = TextAnchor.MiddleCenter;
            row.childControlWidth = row.childControlHeight = true;
            row.childForceExpandWidth = false;
            row.childForceExpandHeight = true;

            // Hide: a small pill on the panel's top rim. Show choice: at the right end of the divider,
            // clear of the rows.
            var hide = Ui.Node("Hide", root);
            hide.gameObject.AddComponent<LayoutElement>().ignoreLayout = true;
            Ui.Anchor(hide, new Vector2(1, 1), new Vector2(1, 0.5f), new Vector2(-18, 0), new Vector2(84, 28));
            var hideButton = Ui.Button(hide, UiText.HideChoice, Palette.Firefly, 13, out var hideLabel);
            hideLabel.characterSpacing = 2f;
            hideButton.onClick.AddListener(() => view.SetCollapsed(true));
            var show = Ui.Node("ShowChoice", parent);
            Ui.Anchor(show, new Vector2(1, 1), new Vector2(1, 0.5f), new Vector2(-24, -DividerY), new Vector2(170, 40));
            var showButton = Ui.Button(show, UiText.ShowChoice, Palette.Firefly, 16, out var showLabel, primary: true);
            showLabel.characterSpacing = 2f;
            showButton.onClick.AddListener(() => view.SetCollapsed(false));
            view._showButton = show.gameObject;
            view._showButton.SetActive(false);
            root.gameObject.SetActive(false);
            return view;
        }

        void SetCollapsed(bool collapsed)
        {
            _collapsed = collapsed;
            gameObject.SetActive(!collapsed);
            _showButton.SetActive(collapsed);
            _showButton.transform.SetAsLastSibling();
        }

        /// <summary>Shows <paramref name="s"/>'s pending choice, which is yours.</summary>
        public void Show(GameState s, IReadOnlyDictionary<string, CardDef> defs)
        {
            var p = s.pending;
            foreach (var go in _built) Destroy(go);
            _built.Clear();
            string shown = $"{p.source}:{p.ability_text}";
            if (shown != _shown) _collapsed = false;
            _shown = shown;
            transform.SetAsLastSibling();
            gameObject.SetActive(true);  // so the layout below can be rebuilt; SetCollapsed hides it again
            string source = defs.TryGetValue(p.card_id, out var def) ? def.name : p.card_id;
            _text.text = $"<b>{source}:</b> {CardText.Ability(p.ability_text).Replace("\n", "  ")}";

            bool targets = false;
            foreach (var a in s.legal_actions)
            {
                if (a.type == ActionTypes.ChooseTarget) targets = true;
                else if (a.type == ActionTypes.Accept || a.type == ActionTypes.Decline)
                {
                    bool no = a.type == ActionTypes.Decline;
                    Answer(a.text, 140, no ? Palette.Muted : Palette.Lantern, !no, a);
                }
                else if (a.type == ActionTypes.ChooseOption && p.options == null)
                    Answer(a.text, 340, Palette.Lantern, true, a);  // a server without the options list
            }
            // "Choose one": every option, the ones with nothing to choose greyed out.
            if (p.options != null)
                foreach (var o in p.options)
                {
                    var answer = Commands.Find(s, a => a.type == ActionTypes.ChooseOption && a.option == o.option);
                    bool usable = o.usable && answer != null;
                    Answer(o.text, 340, usable ? Palette.Lantern : Palette.Muted, usable, usable ? answer : null);
                }
            _hint.gameObject.SetActive(targets);
            _buttons.gameObject.SetActive(_built.Count > 0);
            LayoutRebuilder.ForceRebuildLayoutImmediate((RectTransform)transform);
            SetCollapsed(_collapsed);
        }

        /// <summary>An answer button; with no action it's greyed out and does nothing.</summary>
        void Answer(string text, float width, Color accent, bool primary, GameAction action)
        {
            var rt = Ui.Node("Answer", _buttons);
            var element = rt.gameObject.AddComponent<LayoutElement>();
            element.minWidth = 120;
            element.preferredWidth = width;
            var button = Ui.Button(rt, text, accent, 16, out var label, primary);
            label.characterSpacing = 0f;
            button.onClick.AddListener(() => AnswerChosen?.Invoke(action));
            button.interactable = action != null;
            label.textWrappingMode = TextWrappingModes.Normal;
            _built.Add(rt.gameObject);
        }

        public void Hide()
        {
            gameObject.SetActive(false);
            _showButton.SetActive(false);
            _shown = null;
        }
    }

    /// <summary>
    /// A dev panel to start a scenario with chosen cards (docs/client-protocol.md, new_game). Text like
    /// "hand: C1-004; opponent_play: C1-018; mana: 3" becomes the request's scenario object.
    /// </summary>
    public class DevPanel : MonoBehaviour
    {
        const string PrefKey = "tcg.dev.scenario";
        static readonly string[] Numbers = { "mana", "opponent_mana", "health", "opponent_health" };

        /// <summary>Start: the scenario and an optional seed.</summary>
        public event Action<JObject, int?> ScenarioRequested;

        TMP_InputField _input;
        TMP_Text _error;
        GameObject _panel;

        public static DevPanel Create(RectTransform parent)
        {
            var root = Ui.Stretch("Dev", parent, 0, 0, 0, 0);
            var view = root.gameObject.AddComponent<DevPanel>();
            // Raycasts pass through the full-screen root except on its button and open panel.
            var toggle = Ui.Node("Toggle", root);  // under the help button, top right
            Ui.Anchor(toggle, new Vector2(1, 1), new Vector2(1, 1), new Vector2(-22, -62), new Vector2(48, 22));
            Ui.Pill(toggle, UiText.DevButton, Palette.Glass, 11, display: false);
            var toggleButton = toggle.gameObject.AddComponent<Button>();
            toggleButton.targetGraphic = toggle.GetComponent<Image>();
            toggle.GetComponent<Image>().raycastTarget = true;
            toggleButton.onClick.AddListener(view.Toggle);

            var panel = Ui.Node("Panel", root);
            Ui.Anchor(panel, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(620, 400));
            Ui.Panel(panel, 16, null, 0.96f).raycastTarget = true;
            Ui.Display(Ui.TopStrip("Title", panel, 0, 16, 32), UiText.DevTitle, 24);
            Ui.Text(Ui.TopStrip("Help", panel, 24, 54, 54), UiText.DevHelp, Ui.Theme.Body, 12, Palette.SubtleText,
                TextAlignmentOptions.TopLeft).textWrappingMode = TextWrappingModes.Normal;
            view._input = CreateInput(Ui.TopStrip("Input", panel, 24, 112, 180));
            view._input.text = PlayerPrefs.GetString(PrefKey, UiText.DevDefault);
            view._error = Ui.Text(Ui.TopStrip("Error", panel, 24, 298, 20), "", Ui.Theme.BodyBold, 13,
                Palette.StatDown, TextAlignmentOptions.Left);
            var start = Ui.Node("Start", panel);
            Ui.Anchor(start, new Vector2(1, 0), new Vector2(1, 0), new Vector2(-24, 20), new Vector2(160, 52));
            Ui.Button(start, UiText.DevStart, Palette.Lantern, 18, out _, true).onClick.AddListener(view.OnStartPressed);
            var close = Ui.Node("Close", panel);
            Ui.Anchor(close, new Vector2(1, 0), new Vector2(1, 0), new Vector2(-200, 20), new Vector2(130, 52));
            Ui.Button(close, UiText.DevClose, Palette.Muted, 16, out _)
                .onClick.AddListener(view.Toggle);
            view._panel = panel.gameObject;
            view._panel.SetActive(false);
            return view;
        }

        static TMP_InputField CreateInput(RectTransform rt)
        {
            rt.gameObject.SetActive(false);  // wire it up before TMP_InputField enables
            Ui.Rounded(rt, Palette.TextBox, 10).raycastTarget = true;
            var area = Ui.Stretch("Text Area", rt, 12, 8, 12, 8);
            area.gameObject.AddComponent<RectMask2D>();
            var text = Ui.Text(Ui.Stretch("Text", area, 0, 0, 0, 0), "", Ui.Theme.Body, 16, Palette.BodyText,
                TextAlignmentOptions.TopLeft);
            text.textWrappingMode = TextWrappingModes.Normal;
            var input = rt.gameObject.AddComponent<TMP_InputField>();
            input.textViewport = area;
            input.textComponent = text;
            input.fontAsset = Ui.Theme.Body;
            input.pointSize = 16;
            input.lineType = TMP_InputField.LineType.MultiLineNewline;
            input.targetGraphic = rt.GetComponent<Image>();
            rt.gameObject.SetActive(true);
            return input;
        }

        void Toggle()
        {
            _panel.SetActive(!_panel.activeSelf);
            _error.text = "";
            if (_panel.activeSelf) transform.SetAsLastSibling();
        }

        void OnStartPressed()
        {
            try
            {
                var (scenario, seed) = Parse(_input.text);
                PlayerPrefs.SetString(PrefKey, _input.text);
                _panel.SetActive(false);
                ScenarioRequested?.Invoke(scenario, seed);
            }
            catch (FormatException e)
            {
                _error.text = e.Message;
            }
        }

        /// <summary>"hand: C1-004; play: C1-010 attacked damage=1; mana: 2; seed: 1" → scenario JSON and seed.</summary>
        public static (JObject scenario, int? seed) Parse(string text)
        {
            var scenario = new JObject();
            int? seed = null;
            foreach (var raw in text.Split(new[] { ';', '\n' }, StringSplitOptions.RemoveEmptyEntries))
            {
                var line = raw.Trim();
                if (line.Length == 0) continue;
                int colon = line.IndexOf(':');
                if (colon < 0) throw new FormatException($"Expected key: value in \"{line}\"");
                string key = line.Substring(0, colon).Trim().ToLowerInvariant();
                string value = line.Substring(colon + 1).Trim();
                if (key == "seed" || Array.IndexOf(Numbers, key) >= 0)
                {
                    if (!int.TryParse(value, out int n)) throw new FormatException($"{key} needs a number");
                    if (key == "seed") seed = n;
                    else scenario[key] = n;
                    continue;
                }
                var cards = new JArray();
                foreach (var item in value.Split(new[] { ',' }, StringSplitOptions.RemoveEmptyEntries))
                {
                    var words = item.Trim().Split(new[] { ' ' }, StringSplitOptions.RemoveEmptyEntries);
                    if (words.Length == 0) continue;
                    if (words.Length == 1)
                    {
                        cards.Add(words[0]);
                        continue;
                    }
                    var card = new JObject { ["id"] = words[0] };
                    for (int i = 1; i < words.Length; i++)
                    {
                        if (words[i] == "attacked") card["attacked"] = true;
                        else if (words[i].StartsWith("damage=") && int.TryParse(words[i].Substring(7), out int d)) card["damage"] = d;
                        else throw new FormatException($"Unknown \"{words[i]}\" after {words[0]}");
                    }
                    cards.Add(card);
                }
                scenario[key] = cards;
            }
            return (scenario, seed);
        }
    }
}
