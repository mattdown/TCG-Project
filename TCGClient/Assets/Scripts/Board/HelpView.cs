using System.Collections.Generic;
using Tcg.Protocol;
using Tcg.View;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace Tcg.Board
{
    /// <summary>
    /// The help screen (the mockup's "6 · Help: how to read a card"): a sample unit from the card
    /// set at 2× with a callout for each part, the keywords and the classes. Every rule and name on
    /// it comes from the server's card_set; the callouts aim at the card's own parts, so they
    /// follow layout changes to the card.
    /// </summary>
    public class HelpView : MonoBehaviour
    {
        const float CardScale = 2f;
        static readonly Color Callout = Palette.Gold;
        static readonly Color PanelRing = Palette.Hex("#2E4680");
        static readonly Color BoxRing = Palette.Hex("#26386A");
        static readonly Color CloseLip = Palette.Hex("#A8321F");

        public bool IsOpen => gameObject.activeSelf;

        RectTransform _cardArea, _callouts, _keywords, _classes;
        CardView _card;
        TMP_Text _notes;
        readonly List<GameObject> _built = new List<GameObject>();

        public static HelpView Create(RectTransform parent, CardView prefab)
        {
            var root = Ui.Stretch("Help", parent, 0, 0, 0, 0);
            var view = root.gameObject.AddComponent<HelpView>();
            Ui.Scrim(root, "Scrim", 0.82f).onClick.AddListener(view.Hide);

            // Laid out on the 1280x720 design, centred on wider screens.
            var page = Ui.Node("Page", root);
            Ui.Anchor(page, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(1280, 720));
            var panel = Ui.Box("Panel", page, 24, 24, 1232, 672);
            Ui.Rounded(panel, Palette.Outline, 22).raycastTarget = true;  // taps on the panel don't close it
            Ui.Rounded(Ui.Stretch("Ring", panel, 3, 3, 3, 3), PanelRing, 19);
            Ui.Rounded(Ui.Stretch("Face", panel, 5, 5, 5, 5), Palette.UiNavy, 17);

            Ui.Display(Ui.Box("Title", page, 52, 46, 600, 36), UiText.HelpTitle, 30, TextAlignmentOptions.Left);
            var close = Ui.Box("Close", page, 1184, 44, 44, 44);
            Ui.Button(close, "✕", Palette.OpponentAccent, CloseLip, 22, out _, 12).onClick.AddListener(view.Hide);

            view._cardArea = Ui.Box("CardArea", page, 52, 102, 600, 566);
            view._callouts = Ui.Box("Callouts", page, 52, 102, 600, 566);
            view._card = Instantiate(prefab, view._cardArea);
            view._card.Input.Handler = null;
            view._card.Group.blocksRaycasts = false;
            var rt = view._card.Rect;
            rt.anchorMin = rt.anchorMax = new Vector2(0, 1);
            rt.anchoredPosition = new Vector2(300, -250);  // a 300x420 card with its top-left at (150, 40)
            rt.localScale = Vector3.one * CardScale;

            view._notes = Ui.Text(Ui.Box("Notes", view._cardArea, 120, 478, 360, 80), "", Ui.Theme.Nunito, 13,
                Palette.SubtleText, TextAlignmentOptions.Top);
            view._notes.textWrappingMode = TextWrappingModes.Normal;
            view._notes.lineSpacing = 10f;

            Divider(page, 676);
            view._keywords = Column(page, "Keywords", 701, UiText.HelpKeywords);
            Divider(page, 961);
            view._classes = Column(page, "Classes", 986, UiText.HelpClasses);

            root.gameObject.SetActive(false);
            return view;
        }

        /// <summary>Opens the screen with a sample unit from <paramref name="defs"/> (none: no card).</summary>
        public void Show(IReadOnlyDictionary<string, CardDef> defs)
        {
            foreach (var go in _built) Destroy(go);
            _built.Clear();
            gameObject.SetActive(true);
            transform.SetAsLastSibling();

            var sample = PickSample(defs);
            _card.gameObject.SetActive(sample != null);
            if (sample != null)
            {
                _card.Bind(sample, null);
                _card.SetMark(CardMark.None);
                Canvas.ForceUpdateCanvases();  // the job tag sizes itself: lay it out before aiming at it
                LayoutRebuilder.ForceRebuildLayoutImmediate(_card.TraitTag);
                Callouts();
            }
            _notes.text = Notes();

            foreach (var kv in CardText.Keywords)
            {
                string name = kv.Value.numbered ? $"{kv.Value.name} +N" : kv.Value.name;
                KeywordBox(name, kv.Value.rule);
            }
            foreach (var kv in CardText.Aspects)
                ClassRow(kv.Value.name, kv.Value.description, kv.Key == "neutral" ? Palette.Neutral : Palette.Aspect(Palette.AspectNumber(kv.Key)));
            LayoutRebuilder.ForceRebuildLayoutImmediate(_keywords);
            LayoutRebuilder.ForceRebuildLayoutImmediate(_classes);
        }

        public void Hide() => gameObject.SetActive(false);

        /// <summary>A unit that shows every part: a keyword, ability text and a subtitle, if the set has one.</summary>
        static CardDef PickSample(IReadOnlyDictionary<string, CardDef> defs)
        {
            if (defs == null) return null;
            CardDef best = null;
            int bestScore = -1;
            foreach (var def in defs.Values)
            {
                if (def.IsAction) continue;
                int score = (def.keywords != null && def.keywords.Count > 0 ? 1 : 0)
                          + (def.ability_text != null && def.ability_text.Count > 0 ? 1 : 0)
                          + (!string.IsNullOrEmpty(def.subtitle) ? 1 : 0);
                if (score > bestScore || (score == bestScore && string.CompareOrdinal(def.id, best.id) < 0))
                {
                    best = def;
                    bestScore = score;
                }
            }
            return best;
        }

        static string Notes()
        {
            string charge = CardText.KeywordLabel("charge", 1);
            return string.Format(UiText.HelpNoteStats, ColorUtility.ToHtmlStringRGB(Palette.StatUp),
                       ColorUtility.ToHtmlStringRGB(Palette.StatDown)) + "\n"
                   + string.Format(UiText.HelpNoteFresh, charge) + "\n"
                   + UiText.HelpNoteFrozen;
        }

        // --- the callouts: each label's line ends on the card part it describes

        void Callouts()
        {
            // Points in the callout layer: x right, y down from its top-left (as in the mockup).
            Vector2 At(RectTransform part, float u, float v)
            {
                var r = part.rect;
                var world = part.TransformPoint(new Vector3(r.xMin + r.width * u, r.yMin + r.height * (1f - v)));
                var local = (Vector2)_callouts.InverseTransformPoint(world);
                return new Vector2(local.x, -local.y);
            }

            var cost = At(_card.CostGem, 0.75f, 0.5f);
            var colour = At(_card.FrameEdge.rectTransform, 0f, 0.28f);
            var name = At(_card.NameText.rectTransform, 0.08f, 0.5f);
            var rules = At(_card.BodyText.rectTransform, 0.12f, 0.5f);
            var sword = At(_card.PowerIcon, 0.76f, 0.24f);  // the blade: the sprite is drawn at 45 degrees
            var heart = At(_card.HealthIcon, 0.45f, 0.5f);
            var job = At(_card.TraitTag, 0.92f, 0.5f);

            Label(UiText.HelpCost, UiText.HelpCostText, cost, left: true, labelTop: cost.y - 22);
            Label(UiText.HelpColour, UiText.HelpColourText, colour, left: true, labelTop: colour.y - 22);
            Label(UiText.HelpName, UiText.HelpNameText, name, left: true, labelTop: name.y - 10);
            Label(UiText.HelpRules, UiText.HelpRulesText, rules, left: true, labelTop: rules.y - 24);
            // Attack's label sits above the heart, its line running down to the top of the sword, so it
            // isn't read as the health.
            Label(UiText.HelpAttack, UiText.HelpAttackText, sword, left: false, labelTop: Mathf.Max(8f, sword.y - 100f));
            Label(UiText.HelpHealth, UiText.HelpHealthText, heart, left: false, labelTop: heart.y + 14f);
            Label(UiText.HelpJob, UiText.HelpJobText, job, left: false, labelTop: job.y - 12f);
        }

        void Label(string title, string text, Vector2 target, bool left, float labelTop)
        {
            const float width = 126f;
            float x = left ? 0f : 474f;
            var box = Ui.Box(title, _callouts, x, labelTop, width, 60);
            var align = left ? TextAlignmentOptions.TopRight : TextAlignmentOptions.TopLeft;
            var t = Ui.Text(Ui.Box("Title", box, 0, 0, width, 22), title, Ui.Theme.Lilita, 17, Callout, align);
            var b = Ui.Text(Ui.Box("Text", box, 0, 20, width, 40), text, Ui.Theme.Nunito, 13, Palette.TraitText, align);
            b.textWrappingMode = TextWrappingModes.Normal;
            _built.Add(box.gameObject);

            var from = new Vector2(left ? x + width + 2f : x - 4f, labelTop + 18f);
            Line(from, target);
        }

        void Line(Vector2 from, Vector2 to)
        {
            var d = to - from;
            var line = Ui.Node("Line", _callouts);
            line.anchorMin = line.anchorMax = new Vector2(0, 1);
            line.pivot = new Vector2(0, 0.5f);
            line.anchoredPosition = new Vector2(from.x, -from.y);
            line.sizeDelta = new Vector2(d.magnitude, 2f);
            line.localRotation = Quaternion.Euler(0, 0, -Mathf.Atan2(d.y, d.x) * Mathf.Rad2Deg);
            Ui.Img(line, null, Callout);
            var dot = Ui.Node("Dot", _callouts);
            dot.anchorMin = dot.anchorMax = new Vector2(0, 1);
            dot.anchoredPosition = new Vector2(to.x, -to.y);
            dot.sizeDelta = new Vector2(8, 8);
            Ui.Img(dot, Ui.Theme.Dot, Callout);
            _built.Add(line.gameObject);
            _built.Add(dot.gameObject);
        }

        // --- the keyword and class columns

        static void Divider(RectTransform page, float x) =>
            Ui.Img(Ui.Box("Divider", page, x, 102, 1, 566), null, PanelRing);

        static RectTransform Column(RectTransform page, string name, float x, string title)
        {
            var col = Ui.Box(name, page, x, 102, 236, 566);
            var layout = col.gameObject.AddComponent<VerticalLayoutGroup>();
            layout.spacing = 10;
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;
            var heading = Ui.Display(Ui.Node("Title", col), title, 20, TextAlignmentOptions.Left);
            heading.gameObject.AddComponent<LayoutElement>().minHeight = 26;
            return col;
        }

        void KeywordBox(string name, string rule)
        {
            var box = Ui.Node("Keyword", _keywords);
            Ui.Rounded(box, Palette.Outline, 12);
            Ui.Rounded(Ui.Stretch("Ring", box, 2, 2, 2, 2), BoxRing, 10).gameObject.AddComponent<LayoutElement>().ignoreLayout = true;
            Ui.Rounded(Ui.Stretch("Face", box, 4, 4, 4, 4), Palette.CardNavy, 8).gameObject.AddComponent<LayoutElement>().ignoreLayout = true;
            var layout = box.gameObject.AddComponent<VerticalLayoutGroup>();
            layout.padding = new RectOffset(14, 14, 10, 11);
            layout.spacing = 3;
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;
            Ui.Text(Ui.Node("Name", box), name, Ui.Theme.Lilita, 17, Color.white, TextAlignmentOptions.Left);
            var text = Ui.Text(Ui.Node("Rule", box), rule, Ui.Theme.Nunito, 13, Palette.TraitText, TextAlignmentOptions.TopLeft);
            text.textWrappingMode = TextWrappingModes.Normal;
            _built.Add(box.gameObject);
        }

        void ClassRow(string name, string feel, Color colour)
        {
            var row = Ui.Node("Class", _classes);
            Ui.Rounded(row, Palette.Outline, 12);
            Ui.Rounded(Ui.Stretch("Face", row, 2, 2, 2, 2), Palette.CardNavy, 10).gameObject.AddComponent<LayoutElement>().ignoreLayout = true;
            var layout = row.gameObject.AddComponent<HorizontalLayoutGroup>();
            layout.padding = new RectOffset(9, 10, 8, 8);
            layout.spacing = 10;
            layout.childAlignment = TextAnchor.MiddleLeft;
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = layout.childForceExpandHeight = false;

            var swatch = Ui.Node("Swatch", row);
            var size = swatch.gameObject.AddComponent<LayoutElement>();
            size.minWidth = size.preferredWidth = 30;
            size.minHeight = size.preferredHeight = 30;
            Ui.Rounded(swatch, Palette.Outline, 9);
            var face = Ui.Rounded(Ui.Stretch("Colour", swatch, 2, 2, 2, 2), colour, 7);
            Ui.Rounded(Ui.TopStrip("Shine", face.rectTransform, 3, 1, 3), Color.white.WithAlpha(0.35f), 1.5f);

            var words = Ui.Node("Words", row);
            words.gameObject.AddComponent<LayoutElement>().flexibleWidth = 1;
            var stack = words.gameObject.AddComponent<VerticalLayoutGroup>();
            stack.spacing = 1;
            stack.childControlWidth = stack.childControlHeight = true;
            stack.childForceExpandWidth = true;
            stack.childForceExpandHeight = false;
            Ui.Text(Ui.Node("Name", words), name, Ui.Theme.Lilita, 16, Color.white, TextAlignmentOptions.Left);
            var text = Ui.Text(Ui.Node("Feel", words), feel, Ui.Theme.Nunito, 12, Palette.SubtleText, TextAlignmentOptions.TopLeft);
            text.textWrappingMode = TextWrappingModes.Normal;
            _built.Add(row.gameObject);
        }
    }
}
