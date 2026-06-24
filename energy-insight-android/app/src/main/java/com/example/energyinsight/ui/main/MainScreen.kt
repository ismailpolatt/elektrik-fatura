package com.example.energyinsight.ui.main

import android.net.Uri
import android.webkit.ValueCallback
import android.webkit.WebChromeClient
import android.webkit.WebView
import android.webkit.WebViewClient
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
  Box(modifier = Modifier.fillMaxSize()) {
    AndroidView(
      factory = { ctx ->
        WebView(ctx).apply {
          settings.javaScriptEnabled = true
          settings.domStorageEnabled = true
          settings.allowFileAccess = true
          settings.allowContentAccess = true
          
          webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView?, url: String?): Boolean {
              return false
            }
          }
          
          webChromeClient = object : WebChromeClient() {
            override fun onShowFileChooser(
              webView: WebView?,
              filePathCallback: ValueCallback<Array<Uri>>?,
              fileChooserParams: FileChooserParams?
            ): Boolean {
              MainActivity.fileChooserCallback?.invoke(filePathCallback)
              return true
            }
          }
          
          loadUrl("https://efatura.polathome.com/")
        }
      },
      modifier = Modifier.fillMaxSize()
    )
  }
}
