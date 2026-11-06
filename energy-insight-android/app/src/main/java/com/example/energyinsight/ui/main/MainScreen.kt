package com.example.energyinsight.ui.main

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.Toast
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import androidx.navigation3.runtime.NavKey
import com.example.energyinsight.MainActivity

@Composable
fun MainScreen(
  onItemClick: (NavKey) -> Unit = {},
  modifier: Modifier = Modifier
) {
  var browser by remember { mutableStateOf<WebView?>(null) }

  BackHandler(enabled = browser != null) {
    browser?.let { view ->
      view.evaluateJavascript(
        "(function(){if(typeof handleNativeBack === 'function') return handleNativeBack(); return false;})()"
      ) { handled ->
        if (handled != "true") {
          if (view.canGoBack()) view.goBack()
          else (view.context as? Activity)?.finish()
        }
      }
    }
  }

  DisposableEffect(Unit) {
    onDispose {
      browser?.stopLoading()
      browser?.destroy()
      browser = null
    }
  }

  Box(modifier = modifier.fillMaxSize()) {
    AndroidView(
      factory = { ctx ->
        WebView(ctx).apply {
          settings.javaScriptEnabled = true
          settings.domStorageEnabled = true
          settings.allowFileAccess = false
          settings.allowContentAccess = true

          webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
              if (!request.isForMainFrame) return false
              val uri = request.url
              if (uri.scheme == "https" && uri.host == "efatura.polathome.com") return false
              if (uri.scheme !in listOf("https", "http", "whatsapp", "mailto", "tel")) return true
              try {
                ctx.startActivity(Intent(Intent.ACTION_VIEW, uri))
              } catch (_: ActivityNotFoundException) {
                Toast.makeText(ctx, "Bu bağlantıyı açacak uygulama bulunamadı.", Toast.LENGTH_LONG).show()
              }
              return true
            }
          }

          webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
              webView: WebView?,
              filePathCallback: ValueCallback<Array<Uri>>?,
              fileChooserParams: FileChooserParams?
            ): Boolean {
              val callback = MainActivity.fileChooserCallback ?: return false
              callback.invoke(filePathCallback)
              return true
            }
          }

          browser = this
          loadUrl("https://efatura.polathome.com/")
        }
      },
      modifier = Modifier.fillMaxSize()
    )
  }
}
