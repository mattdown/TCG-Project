using System;
using System.Collections.Generic;
using Tcg.Protocol;
using Tcg.View;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Tcg.Board
{
    /// <summary>
    /// Tap to inspect (the mockup's "Landscape inspect"): the card at about 2x over a dimmed board,
    /// a box for anything that needs explaining, and PLAY / ADD ENERGY for hand cards, enabled only
    /// when the matching legal action exists. Tap anywhere to close.
    /// </summary>
    public class InspectView : MonoBehaviour
    {
        const float Scale = 2.1f;
        static readonly Color ChipOpponent = Palette.Hex("#A8321F");
        static readonly Color ChipNeutral = Palette.Hex("#2E4680");
        static readonly Color PlayFace = Palette.Hex("#5BC84E"), PlayLip = Palette.Hex("#2F8A27");
        static readonly Color EnergyLip = Palette.Hex("#A32A9A");

        public event Action<int> ActionChosen;
        public bool IsOpen => gameObject.activeSelf;

        CardView _card;
        RectTransform _chips, _column, _buttons;
        Button _play, _energy;
        TMP_Text _playText;
        GameObject _note;
        readonly List<GameObject> _built = new List<GameObject>();
        GameAction _playAction, _energyAction;

        public static InspectView Create(RectTransform parent, CardView prefab)
        {
            var root = Ui.Stretch("Inspect", parent, 0, 0, 0, 0);
            var view = root.gameObject.AddComponent<InspectView>();
            Ui.Scrim(root, "Scrim", 0.8f).onClick.AddListener(view.Hide);

            var holder = Ui.Box("Card", root, 300, 122, CardView.Width * Scale, CardView.Height * Scale);
            view._card = Instantiate(prefab, holder);
            view._card.Rect.anchorMin = view._card.Rect.anchorMax = new Vector2(0.5f, 0.5f);
            view._card.Rect.anchoredPosition = Vector2.zero;
            view._card.Rect.localScale = Vector3.one * Scale;
            view._card.Group.blocksRaycasts = false;  // taps go through to the scrim

            view._chips = Ui.Box("Chips", root, 300, 62, 700, 30);
            var chipLayout = view._chips.gameObject.AddComponent<HorizontalLayoutGroup>();
            chipLayout.spacing = 6;
            chipLayout.childControlWidth = chipLayout.childControlHeight = false;
            chipLayout.childForceExpandWidth = chipLayout.childForceExpandHeight = false;

            view._column = Ui.Box("Column", root, 660, 122, 340, 400);
            var col = view._column.gameObject.AddComponent<VerticalLayoutGroup>();
            col.spacing = 12;
            col.childControlWidth = col.childControlHeight = true;
            col.childForceExpandWidth = true;
            col.childForceExpandHeight = false;
            view._column.gameObject.AddComponent<ContentSizeFitter>().verticalFit = ContentSizeFitter.FitMode.PreferredSize;

            view._buttons = Ui.Node("Buttons", view._column);
            var buttonsSize = view._buttons.gameObject.AddComponent<LayoutElement>();
            buttonsSize.minHeight = buttonsSize.preferredHeight = 66;
            buttonsSize.flexibleHeight = 0;
            var row = view._buttons.gameObject.AddComponent<HorizontalLayoutGroup>();
            row.spacing = 12;
            row.padding = new RectOffset(0, 0, 10, 0);
            row.childControlWidth = row.childControlHeight = true;
            row.childForceExpandWidth = row.childForceExpandHeight = true;
            view._play = Ui.Button(Ui.Node("Play", view._buttons), "PLAY", PlayFace, PlayLip, 19, out view._playText);
            view._play.onClick.AddListener(() => view.Choose(view._playAction));
            view._energy = Ui.Button(Ui.Node("Energy", view._buttons), UiText.AddEnergyButton, Palette.Energy, EnergyLip, 19, out _);
            view._energy.onClick.AddListener(() => view.Choose(view._energyAction));
            view._note = Ui.Body(Ui.Node("Note", view._column), UiText.ButtonsNote, 13, Palette.SubtleText).gameObject;

            Ui.Body(Ui.TopStrip("Hint", root, 0, 652, 24), UiText.TapToClose, 14, Palette.SubtleText,
                TextAlignmentOptions.Center);
            root.gameObject.SetActive(false);
            return view;
        }

        public void Show(CardDef def, CardInstance instance, string owner, bool inHand, GameState s)
        {
            foreach (var go in _built) Destroy(go);
            _built.Clear();
            gameObject.SetActive(true);
            transform.SetAsLastSibling();
            _card.Bind(def, instance);
            _card.SetMark(CardMark.None);

            Chip(owner, owner == UiText.OpponentsUnit ? ChipOpponent : owner == UiText.YourUnit ? Palette.HumanAccent : ChipNeutral);
            if (!inHand && instance != null)
            {
                if (instance.exhausted) Chip(UiText.Exhausted, ChipNeutral);
                if (instance.fresh) Chip(UiText.Fresh, ChipNeutral);
                if (instance.damage > 0) Chip(string.Format(UiText.DamageChip, instance.damage), ChipNeutral);
            }

            // Vanilla cards: only the cost gem's rim needs explaining, plus any damage taken.
            int index = 0;
            if (def.energy_source) Tip(UiText.EnergySourceTitle, UiText.EnergySourceText, index++);
            else Tip(UiText.NotEnergySourceTitle, UiText.NotEnergySourceText, index++);
            if (instance != null && instance.damage > 0)
                Tip(string.Format(UiText.HealthTitle, def.health - instance.damage, def.health),
                    string.Format(UiText.HealthText, instance.damage), index++);

            _buttons.gameObject.SetActive(inHand);
            _note.SetActive(inHand);
            if (inHand)
            {
                _playAction = _energyAction = null;
                foreach (var a in s.legal_actions)
                {
                    if (a.card != instance?.uid) continue;
                    if (a.type == ActionTypes.Play) _playAction = a;
                    if (a.type == ActionTypes.AddEnergy) _energyAction = a;
                }
                int cost = _playAction?.preview != null ? _playAction.preview.EnergyFor(s.human_seat) : def.cost;
                _playText.text = string.Format(UiText.PlayButton, cost);
                _play.interactable = _playAction != null;
                _energy.interactable = _energyAction != null;
            }
            LayoutRebuilder.ForceRebuildLayoutImmediate(_column);
        }

        public void Hide() => gameObject.SetActive(false);

        void Choose(GameAction action)
        {
            if (action == null) return;
            Hide();
            ActionChosen?.Invoke(action.index);
        }

        void Chip(string text, Color background)
        {
            var rt = Ui.Node("Chip", _chips);
            Ui.Pill(rt, text, background, 13, display: false);
            _built.Add(rt.gameObject);
        }

        void Tip(string title, string text, int index)
        {
            var rt = Ui.Node("Tip", _column);
            rt.SetSiblingIndex(index);
            Ui.Rounded(rt, Palette.Outline, 12);
            var ring = Ui.Rounded(Ui.Stretch("Ring", rt, 3, 3, 3, 3), ChipNeutral, 9);
            ring.gameObject.AddComponent<LayoutElement>().ignoreLayout = true;
            var face = Ui.Rounded(Ui.Stretch("Face", rt, 5, 5, 5, 5), Palette.CardNavy, 7);
            face.gameObject.AddComponent<LayoutElement>().ignoreLayout = true;
            var layout = rt.gameObject.AddComponent<VerticalLayoutGroup>();
            layout.padding = new RectOffset(16, 16, 12, 14);
            layout.spacing = 3;
            layout.childControlWidth = layout.childControlHeight = true;
            layout.childForceExpandWidth = true;
            layout.childForceExpandHeight = false;
            Ui.Display(Ui.Node("Title", rt), title, 18, TextAlignmentOptions.Left);
            var body = Ui.Text(Ui.Node("Text", rt), text, Ui.Theme.Nunito, 14, Palette.TraitText, TextAlignmentOptions.TopLeft);
            body.textWrappingMode = TextWrappingModes.Normal;
            _built.Add(rt.gameObject);
        }
    }

    /// <summary>
    /// The mulligan (not designed yet, kept simple): the hand large, tap a card to put it back via
    /// its legal mulligan action, then KEEP. The server can't unmark a card, so a marked card stays marked.
    /// </summary>
    public class MulliganView : MonoBehaviour, ICardInputHandler
    {
        const float Spacing = 162f;
        static readonly Color BadgeRed = Palette.Hex("#C42A3A");

        public event Action<int> ActionChosen;

        RectTransform _cards;
        CardView _prefab;
        Button _keep;
        TMP_Text _keepText;
        readonly Dictionary<int, CardView> _views = new Dictionary<int, CardView>();
        GameState _state;
        GameAction _keepAction;

        public static MulliganView Create(RectTransform parent, CardView prefab)
        {
            var root = Ui.Stretch("Mulligan", parent, 0, 0, 0, 0);
            var view = root.gameObject.AddComponent<MulliganView>();
            view._prefab = prefab;
            Ui.Scrim(root, "Scrim", 0.82f).interactable = false;
            Ui.Display(Ui.TopStrip("Title", root, 0, 70, 40), UiText.MulliganTitle, 32);
            Ui.Body(Ui.TopStrip("Text", root, 0, 116, 24), UiText.MulliganText, 16, Palette.SubtleText,
                TextAlignmentOptions.Center);
            view._cards = Ui.Node("Cards", root);
            Ui.Anchor(view._cards, new Vector2(0.5f, 1), new Vector2(0.5f, 0.5f), new Vector2(0, -345), Vector2.zero);
            var keep = Ui.Node("Keep", root);
            Ui.Anchor(keep, new Vector2(0.5f, 1), new Vector2(0.5f, 1), new Vector2(0, -560), new Vector2(220, 60));
            view._keep = Ui.Button(keep, UiText.Keep, Palette.Gold, Palette.GoldLip, 22, out view._keepText);
            view._keep.onClick.AddListener(() =>
            {
                if (view._keepAction != null) view.ActionChosen?.Invoke(view._keepAction.index);
            });
            root.gameObject.SetActive(false);
            return view;
        }

        public void Show(GameState s, IReadOnlyDictionary<string, CardDef> defs)
        {
            _state = s;
            gameObject.SetActive(true);
            transform.SetAsLastSibling();
            var hand = s.Human.hand ?? new List<CardInstance>();
            var marked = new HashSet<int>(s.Human.mulligan_marked ?? new List<int>());
            var seen = new HashSet<int>();
            _keepAction = null;
            foreach (var a in s.legal_actions)
                if (a.type == ActionTypes.KeepHand) _keepAction = a;

            for (int i = 0; i < hand.Count; i++)
            {
                var c = hand[i];
                seen.Add(c.uid);
                if (!_views.TryGetValue(c.uid, out var v))
                {
                    v = Instantiate(_prefab, _cards);
                    v.Input.Handler = this;
                    _views[c.uid] = v;
                }
                if (defs.TryGetValue(c.card_id, out var def)) v.Bind(def, c);
                v.Rect.anchoredPosition = new Vector2((i - (hand.Count - 1) / 2f) * Spacing, 0f);
                bool isMarked = marked.Contains(c.uid);
                v.SetDimmed(isMarked);
                v.SetBadge(isMarked ? UiText.PutBack : null, BadgeRed);
            }
            var gone = new List<int>();
            foreach (var kv in _views) if (!seen.Contains(kv.Key)) gone.Add(kv.Key);
            foreach (int uid in gone)
            {
                Destroy(_views[uid].gameObject);
                _views.Remove(uid);
            }
            _keepText.text = _keepAction != null ? _keepAction.text.ToUpperInvariant() : UiText.Keep;
            _keep.interactable = _keepAction != null;
        }

        public void Hide()
        {
            if (!gameObject.activeSelf) return;
            gameObject.SetActive(false);
            foreach (var v in _views.Values) Destroy(v.gameObject);
            _views.Clear();
        }

        public void OnCardTap(CardView card)
        {
            if (_state == null) return;
            foreach (var a in _state.legal_actions)
                if (a.type == ActionTypes.Mulligan && a.card == card.Uid)
                {
                    ActionChosen?.Invoke(a.index);
                    return;
                }
        }

        public bool OnCardDragStart(CardView card, PointerEventData e) => false;
        public void OnCardDrag(CardView card, PointerEventData e) { }
        public void OnCardDragEnd(CardView card, PointerEventData e) { }
    }

    /// <summary>Game over (not designed yet, kept simple): the result, final VP and NEW GAME.</summary>
    public class GameOverView : MonoBehaviour
    {
        public event Action NewGameRequested;
        TMP_Text _title, _score;

        public static GameOverView Create(RectTransform parent)
        {
            var root = Ui.Stretch("GameOver", parent, 0, 0, 0, 0);
            var view = root.gameObject.AddComponent<GameOverView>();
            Ui.Scrim(root, "Scrim", 0.7f).interactable = false;
            var panel = Ui.Node("Panel", root);
            Ui.Anchor(panel, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0, 20), new Vector2(460, 270));
            Ui.Rounded(panel, Palette.Outline, 18);
            Ui.Rounded(Ui.Stretch("Ring", panel, 3, 3, 3, 3), Palette.Hex("#2E4680"), 15);
            Ui.Rounded(Ui.Stretch("Face", panel, 6, 6, 6, 6), Palette.UiNavy, 12);
            view._title = Ui.Display(Ui.TopStrip("Title", panel, 0, 34, 60), "", 48);
            view._title.color = Palette.Gold;
            view._score = Ui.Text(Ui.TopStrip("Score", panel, 0, 104, 30), "", Ui.Theme.NunitoBlack, 20, Color.white,
                TextAlignmentOptions.Center);
            var button = Ui.Node("NewGame", panel);
            Ui.Anchor(button, new Vector2(0.5f, 0), new Vector2(0.5f, 0), new Vector2(0, 30), new Vector2(220, 60));
            Ui.Button(button, UiText.NewGame, Palette.Gold, Palette.GoldLip, 22, out _)
                .onClick.AddListener(() => view.NewGameRequested?.Invoke());
            root.gameObject.SetActive(false);
            return view;
        }

        public void Show(GameState s, string opponentName)
        {
            gameObject.SetActive(true);
            transform.SetAsLastSibling();
            _title.text = s.winner == null ? UiText.Draw : s.winner == s.human_seat ? UiText.YouWin : UiText.YouLose;
            _score.text = string.Format(UiText.FinalScore, UiText.You, s.Human.vp, opponentName, s.Opponent.vp);
        }

        public void Hide() => gameObject.SetActive(false);
    }
}
