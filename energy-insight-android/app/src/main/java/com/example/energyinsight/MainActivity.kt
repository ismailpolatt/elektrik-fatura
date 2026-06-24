package com.example.energyinsight

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.webkit.ValueCallback
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import com.example.energyinsight.theme.EnergyInsightTheme

class MainActivity : ComponentActivity() {

  private var fileUploadCallback: ValueCallback<Array<Uri>>? = null

  private val fileChooserLauncher = registerForActivityResult(
      ActivityResultContracts.StartActivityForResult()
  ) { result ->
      val results = if (result.resultCode == Activity.RESULT_OK) {
          val data = result.data
          when {
              data?.clipData != null -> {
                  val count = data.clipData!!.itemCount
                  val uris = ArrayList<Uri>()
                  for (i in 0 until count) {
                      data.clipData!!.getItemAt(i).uri?.let { uris.add(it) }
                  }
                  uris.toTypedArray()
              }
              data?.data != null -> {
                  arrayOf(data.data!!)
              }
              else -> null
          }
      } else null
      
      fileUploadCallback?.onReceiveValue(results)
      fileUploadCallback = null
  }

  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    
    // Set static bridge callback
    fileChooserCallback = { callback ->
        fileUploadCallback?.onReceiveValue(null) // Cancel previous
        fileUploadCallback = callback
        
        val intent = Intent(Intent.ACTION_GET_CONTENT).apply {
            addCategory(Intent.CATEGORY_OPENABLE)
            type = "*/*" // allow all files
            putExtra(Intent.EXTRA_ALLOW_MULTIPLE, false)
        }
        fileChooserLauncher.launch(Intent.createChooser(intent, "Fatura Seç"))
    }

    enableEdgeToEdge()
    setContent {
      EnergyInsightTheme { 
        Surface(modifier = Modifier.fillMaxSize(), color = MaterialTheme.colorScheme.background) { 
          MainNavigation() 
        } 
      }
    }
  }

  override fun onDestroy() {
    super.onDestroy()
    fileChooserCallback = null
  }

  companion object {
    var fileChooserCallback: ((ValueCallback<Array<Uri>>?) -> Unit)? = null
  }
}
