package fr.musicotheque.remote;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.nsd.NsdManager;
import android.net.nsd.NsdServiceInfo;
import android.net.wifi.WifiManager;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.TextView;

import java.net.InetAddress;
import java.util.ArrayList;
import java.util.LinkedList;
import java.util.List;

/**
 * Télécommande Musicothèque.
 * 1. Trouve les Raspberry Pi « Musicothèque » sur le Wi-Fi (service réseau _musicotheque._tcp),
 *    ou accepte une adresse saisie à la main (ex. 192.168.1.20:8080).
 * 2. Affiche la télécommande servie par le Raspberry Pi (le code d'appairage est demandé la 1re fois).
 */
public class MainActivity extends Activity {
    private static final String SERVICE = "_musicotheque._tcp.";
    private static final int BG = Color.rgb(13, 17, 23), CARD = Color.rgb(22, 27, 34),
            TXT = Color.rgb(230, 237, 243), DIM = Color.rgb(139, 148, 158), BLUE = Color.rgb(31, 111, 235);

    private SharedPreferences prefs;
    private WebView web;
    private LinearLayout setup;
    private TextView status;
    private EditText manual;
    private final List<String> names = new ArrayList<>();
    private final List<String> urls = new ArrayList<>();
    private ArrayAdapter<String> adapter;

    private NsdManager nsd;
    private NsdManager.DiscoveryListener discovery;
    private WifiManager.MulticastLock lock;
    private final LinkedList<NsdServiceInfo> toResolve = new LinkedList<>();
    private boolean resolving = false;
    private final Handler ui = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle b) {
        super.onCreate(b);
        getWindow().setStatusBarColor(BG);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        prefs = getSharedPreferences("musicotheque", MODE_PRIVATE);
        buildSetup();
        buildWeb();
        String saved = prefs.getString("server", null);
        if (saved != null) openServer(saved); else showSetup(null);
    }

    // ------------------------------------------------------------------ écran de recherche
    private void buildSetup() {
        setup = new LinearLayout(this);
        setup.setOrientation(LinearLayout.VERTICAL);
        setup.setBackgroundColor(BG);
        int p = dp(20);
        setup.setPadding(p, dp(28), p, p);

        TextView title = text("♪ Musicothèque", 28, TXT);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        setup.addView(title);
        setup.addView(text("Télécommande", 16, DIM));

        status = text("Recherche des Musicothèque sur le Wi-Fi…", 15, TXT);
        status.setPadding(0, dp(22), 0, dp(8));
        setup.addView(status);

        adapter = new ArrayAdapter<String>(this, android.R.layout.simple_list_item_1, names) {
            @Override public View getView(int pos, View v, ViewGroup parent) {
                TextView t = (TextView) super.getView(pos, v, parent);
                t.setTextColor(TXT); t.setTextSize(18); t.setBackgroundColor(CARD);
                t.setPadding(dp(16), dp(16), dp(16), dp(16));
                return t;
            }
        };
        ListView list = new ListView(this);
        list.setAdapter(adapter);
        list.setDividerHeight(dp(6));
        list.setOnItemClickListener((parent, view, pos, id) -> openServer(urls.get(pos)));
        setup.addView(list, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, 0, 1f));

        setup.addView(text("Ou saisissez l'adresse affichée sur le Raspberry Pi (Outils ▸ Télécommande) :", 14, DIM));
        manual = new EditText(this);
        manual.setHint("ex. 192.168.1.20:8080");
        manual.setHintTextColor(DIM);
        manual.setTextColor(TXT);
        manual.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        manual.setSingleLine(true);
        setup.addView(manual);

        LinearLayout row = new LinearLayout(this);
        Button go = button("Se connecter", BLUE);
        go.setOnClickListener(v -> {
            String a = manual.getText().toString().trim();
            if (a.isEmpty()) return;
            if (!a.startsWith("http")) a = "http://" + a;
            if (!a.matches("^https?://[^/]+:\\d+.*")) a = a.replaceAll("/+$", "") + ":8080";
            openServer(a);
        });
        Button again = button("Rechercher", CARD);
        again.setOnClickListener(v -> startDiscovery());
        row.addView(go, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        row.addView(again, new LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f));
        setup.addView(row);
    }

    private void buildWeb() {
        web = new WebView(this);
        web.setBackgroundColor(BG);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);         // garde le jeton d'appairage
        s.setMediaPlaybackRequiresUserGesture(false);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public void onReceivedError(WebView view, WebResourceRequest req, WebResourceError err) {
                if (req.isForMainFrame()) {
                    showSetup("Musicothèque injoignable (" + err.getDescription() + "). "
                            + "Vérifiez que le téléphone est sur le même Wi-Fi et que le Raspberry Pi est allumé.");
                }
            }
        });
    }

    private void showSetup(String message) {
        setContentView(setup);
        names.clear(); urls.clear(); adapter.notifyDataSetChanged();
        if (message != null) status.setText(message);
        String saved = prefs.getString("server", null);
        if (saved != null && manual.getText().length() == 0) manual.setText(saved.replace("http://", ""));
        startDiscovery();
    }

    private void openServer(String url) {
        stopDiscovery();
        if (!url.endsWith("/")) url = url + "/";
        prefs.edit().putString("server", url).apply();
        if (web.getParent() == null) setContentView(web);
        web.loadUrl(url);
    }

    @Override
    public void onBackPressed() {
        if (web.getParent() != null) {
            if (web.canGoBack()) { web.goBack(); return; }
            new AlertDialog.Builder(this)
                    .setTitle("Musicothèque")
                    .setItems(new CharSequence[]{"Changer de Musicothèque", "Quitter"}, (d, which) -> {
                        if (which == 0) showSetup("Recherche des Musicothèque sur le Wi-Fi…");
                        else finish();
                    }).show();
            return;
        }
        super.onBackPressed();
    }

    // ------------------------------------------------------------------ découverte réseau (mDNS)
    private void startDiscovery() {
        stopDiscovery();
        status.setText("Recherche des Musicothèque sur le Wi-Fi…");
        WifiManager wifi = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
        if (wifi != null) {
            lock = wifi.createMulticastLock("musicotheque");
            lock.setReferenceCounted(false);
            lock.acquire();
        }
        nsd = (NsdManager) getSystemService(Context.NSD_SERVICE);
        discovery = new NsdManager.DiscoveryListener() {
            @Override public void onDiscoveryStarted(String type) { }
            @Override public void onDiscoveryStopped(String type) { }
            @Override public void onStartDiscoveryFailed(String type, int code) {
                ui.post(() -> status.setText("Recherche impossible : saisissez l'adresse ci-dessous."));
            }
            @Override public void onStopDiscoveryFailed(String type, int code) { }
            @Override public void onServiceFound(NsdServiceInfo info) {
                synchronized (toResolve) { toResolve.add(info); }
                ui.post(MainActivity.this::resolveNext);
            }
            @Override public void onServiceLost(NsdServiceInfo info) { }
        };
        try {
            nsd.discoverServices(SERVICE, NsdManager.PROTOCOL_DNS_SD, discovery);
        } catch (Exception e) {
            status.setText("Recherche impossible : saisissez l'adresse ci-dessous.");
        }
        ui.postDelayed(() -> {
            if (setup.getParent() != null && urls.isEmpty())
                status.setText("Aucune Musicothèque trouvée pour l'instant. Même Wi-Fi ? Sinon, saisissez l'adresse.");
        }, 8000);
    }

    /** Android ne résout qu'un service à la fois : on les traite l'un après l'autre. */
    private void resolveNext() {
        NsdServiceInfo next;
        synchronized (toResolve) {
            if (resolving || toResolve.isEmpty()) return;
            next = toResolve.removeFirst();
            resolving = true;
        }
        nsd.resolveService(next, new NsdManager.ResolveListener() {
            @Override public void onResolveFailed(NsdServiceInfo info, int code) {
                ui.post(() -> { resolving = false; resolveNext(); });
            }
            @Override public void onServiceResolved(NsdServiceInfo info) {
                InetAddress h = info.getHost();
                String host = h.getHostAddress();
                if (host != null && host.contains(":")) host = "[" + host + "]";
                String url = "http://" + host + ":" + info.getPort() + "/";
                String name = info.getServiceName();
                ui.post(() -> {
                    if (!urls.contains(url)) {
                        urls.add(url); names.add(name + "\n" + url.replace("http://", "").replaceAll("/$", ""));
                        adapter.notifyDataSetChanged();
                        status.setText("Touchez votre Musicothèque :");
                    }
                    resolving = false; resolveNext();
                });
            }
        });
    }

    private void stopDiscovery() {
        if (nsd != null && discovery != null) {
            try { nsd.stopServiceDiscovery(discovery); } catch (Exception ignored) { }
        }
        discovery = null;
        synchronized (toResolve) { toResolve.clear(); resolving = false; }
        if (lock != null && lock.isHeld()) lock.release();
    }

    @Override protected void onDestroy() { stopDiscovery(); super.onDestroy(); }

    // ------------------------------------------------------------------ petits outils d'interface
    private int dp(int v) { return Math.round(v * getResources().getDisplayMetrics().density); }

    private TextView text(String s, int size, int color) {
        TextView t = new TextView(this);
        t.setText(s); t.setTextSize(size); t.setTextColor(color);
        return t;
    }

    private Button button(String s, int color) {
        Button b = new Button(this);
        b.setText(s); b.setTextColor(TXT); b.setAllCaps(false); b.setTextSize(16);
        b.setBackgroundColor(color);
        b.setGravity(Gravity.CENTER);
        return b;
    }
}
